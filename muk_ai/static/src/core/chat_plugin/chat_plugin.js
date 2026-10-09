import {
    EventBus,
    onWillDestroy,
    Plugin,
    proxy,
    signal,
    untrack,
    useEffect,
    usePlugin,
} from '@odoo/owl';

import { BusPlugin } from '@bus/services/bus_plugin';
import { DialogPlugin } from '@web/core/dialog/dialog_plugin';
import { deserializeDateTime } from '@web/core/l10n/dates';
import { _t } from '@web/core/l10n/translation';
import { NotificationPlugin } from '@web/core/notifications/notification_plugin';
import { ORM } from '@web/core/orm_plugin';
import { registry } from '@web/core/registry';
import { services } from '@web/core/services';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { AISession } from '@muk_ai/core/session/session';
import { formatError } from '@muk_ai/core/utils/utils';

const NOTIFICATION_FRESHNESS_MS = 2 * 60 * 1000;
const TARGET_TIMEOUT_MS = 2000;
const TARGET_POLL_MS = 100;

/**
 * The AI chats of this tab: one `AISession` per chat shared by every surface,
 * the floating windows, the sidebar rows and the unread badge, fed by one
 * subscription per bus notification type.
 *
 * `events` re-dispatches `session_state` notifications and announces chats
 * created here as `created`, for the lists that have to react.
 */
export class AIChatPlugin extends Plugin {
    action = usePlugin(ActionPlugin);
    bus = usePlugin(BusPlugin);
    dialog = usePlugin(DialogPlugin);
    notification = usePlugin(NotificationPlugin);
    orm = usePlugin(ORM);
    events = new EventBus();
    sessions = new Map();
    windows = proxy([]);
    rows = proxy({});
    badge = proxy({ count: 0, unreadIds: [], spaceUnread: {} });
    agents = signal([]);
    pageSessionId = null;
    targets = [];
    toasts = new Map();
    setup() {
        const handlers = {
            'muk_ai.event': (event) =>
                this.sessions.get(event.session_id)?.onBusEvent(event),
            'muk_ai.session_state': (payload) => this.onSessionState(payload),
            'muk_ai.notification_badge': (payload) => this.applyBadge(payload, true),
            'muk_ai.session_notification': (payload) => this.onNotification(payload),
        };
        for (const [type, handler] of Object.entries(handlers)) {
            onWillDestroy(this.bus.subscribe(type, handler));
        }
    }
    get windowIds() {
        return this.windows.map((window) => window.id);
    }
    /**
     * Return the client copy of a chat, creating it unloaded.
     * @param {number} id the chat
     * @returns {AISession} the session
     */
    session(id) {
        if (!this.sessions.has(id)) {
            this.sessions.set(id, new AISession(this, id));
        }
        return this.sessions.get(id);
    }
    /**
     * Start showing a chat: follow its channel, load it and clear its
     * notifications when it was not on screen yet.
     * @param {number} id the chat
     * @returns {AISession} the session
     */
    acquire(id) {
        const session = this.session(id);
        if (!session.holders++) {
            this.bus.addChannel(`muk_ai.session_${id}`);
            session.load();
            this.dismiss(id);
        }
        return session;
    }
    /**
     * Stop showing a chat, letting its channel go once nothing shows it.
     * @param {number} id the chat
     */
    release(id) {
        const session = this.sessions.get(id);
        if (session && !--session.holders) {
            this.bus.deleteChannel(`muk_ai.session_${id}`);
        }
    }
    /**
     * Drop a chat the user lost access to from every surface.
     * @param {number} id the chat
     */
    forget(id) {
        this.onSessionState({ session_id: id, deleted: true });
    }
    /**
     * Apply a `muk_ai.session_state` notification to the rows and sessions.
     * A chat on screen takes its state from its own channel only, whose
     * events keep their order.
     * @param {object} payload `{session_id, deleted}` or the state values
     */
    onSessionState(payload) {
        const { session_id: id, deleted, ...values } = payload;
        const session = this.sessions.get(id);
        if (deleted) {
            delete this.rows[id];
            this.closeWindow(id);
            if (session?.holders) {
                this.bus.deleteChannel(`muk_ai.session_${id}`);
            }
            this.sessions.delete(id);
        } else {
            if (this.rows[id]) {
                Object.assign(this.rows[id], values.name ? { name: values.name } : {}, {
                    state: values.state || this.rows[id].state,
                });
            }
            if (session) {
                const { state, ...rest } = values;
                Object.assign(session.data, session.holders ? rest : values);
            }
        }
        this.events.trigger('session_state', payload);
    }
    /**
     * Rename a chat everywhere it is shown.
     * @param {number} id the chat
     * @param {string} name the new name
     */
    async rename(id, name) {
        await this.orm.write('muk_ai.session', [id], { name });
        if (this.rows[id]) {
            this.rows[id].name = name;
        }
        if (this.sessions.has(id)) {
            this.sessions.get(id).data.name = name;
        }
    }
    /**
     * Delete a chat and drop it from every surface.
     * @param {number} id the chat
     */
    async remove(id) {
        await this.orm.unlink('muk_ai.session', [id]);
        this.forget(id);
    }
    /**
     * Merge freshly read sidebar or systray records into the shared rows.
     * @param {Array} records `muk_ai.session` records
     */
    setRows(records) {
        for (const record of records) {
            this.rows[record.id] = { ...this.rows[record.id], ...record };
        }
    }
    /**
     * Load the unread badge once; the bus keeps it current afterwards.
     * @returns {Promise<void>}
     */
    loadBadge() {
        this.badgeLoad ||= this.orm.silent
            .call('muk_ai.session', 'notification_badge', [])
            .then((payload) => this.applyBadge(payload))
            .catch(() => {});
        return this.badgeLoad;
    }
    applyBadge(payload, pushed = false) {
        if (pushed || !this.badgePushed) {
            this.badgePushed ||= pushed;
            Object.assign(this.badge, {
                count: payload.count ?? payload.session_ids.length,
                unreadIds: payload.session_ids,
                spaceUnread: payload.space_unread || {},
            });
        }
    }
    /**
     * Load the active agents once.
     * @returns {Promise<Array>} `{id, name, description, suggestions}` records
     */
    loadAgents() {
        this.agentsLoad ||= this.orm
            .searchRead(
                'muk_ai.agent',
                [['active', '=', true]],
                ['id', 'name', 'description', 'suggestions'],
                { order: 'sequence, name' },
            )
            .catch(() => [])
            .then((agents) => {
                this.agents.set(agents);
                return agents;
            });
        return this.agentsLoad;
    }
    /**
     * Mark a chat's inbox notifications read and close its toasts.
     * @param {number} id the chat
     */
    dismiss(id) {
        this.orm.silent
            .call('muk_ai.session', 'dismiss_notifications', [[id]])
            .catch(() => {});
        for (const close of this.toasts.get(id) || []) {
            close();
        }
        this.toasts.delete(id);
    }
    /**
     * Toast a finished or waiting chat, unless it is already on screen here,
     * this tab is hidden, or the notification is a stale replay.
     * @param {object} payload the `muk_ai.session_notification` payload
     */
    onNotification(payload) {
        const id = payload.session_id;
        const visible = document.visibilityState === 'visible';
        if (this.sessions.get(id)?.holders && visible) {
            this.dismiss(id);
            return;
        }
        const emitted = payload.at ? deserializeDateTime(payload.at).toMillis() : NaN;
        if (!visible || Date.now() - emitted > NOTIFICATION_FRESHNESS_MS) {
            return;
        }
        const types = { error: 'danger', waiting: 'warning' };
        const close = this.notification.add(payload.message, {
            type: types[payload.state] || 'success',
            title: payload.session_name,
            sticky: payload.state !== 'done',
            buttons: [{ name: _t('Open'), onClick: () => this.openFullChat(id) }],
        });
        if (payload.state !== 'done') {
            this.toasts.set(id, [...(this.toasts.get(id) || []), close]);
        }
    }
    /**
     * Create a chat, pin the view on screen to it and announce it.
     * @param {object} [values] extra values of the new `muk_ai.session`
     * @returns {Promise<number>} the new chat
     */
    async createSession(values = {}) {
        const [id] = await this.orm.create('muk_ai.session', [
            { name: _t('Chat %s', new Date().toLocaleString()), ...values },
        ]);
        await this.seedContext(id);
        this.events.trigger('created', { id });
        return id;
    }
    openFullChat(id = null) {
        return this.action.doAction({
            type: 'ir.actions.client',
            tag: 'muk_ai.chat',
            params: id ? { session_id: id } : {},
        });
    }
    /**
     * Open a chat in a floating window, pinning the current view to it.
     * @param {number} id the chat
     */
    openWindow(id) {
        const known = this.windows.find((window) => window.id === id);
        if (known) {
            known.minimized = false;
            return;
        }
        this.windows.push({ id, minimized: false });
        this.seedContext(id);
    }
    closeWindow(id) {
        const index = this.windows.findIndex((window) => window.id === id);
        if (index >= 0) {
            this.windows.splice(index, 1);
        }
    }
    toggleWindow(id) {
        const known = this.windows.find((window) => window.id === id);
        if (known) {
            known.minimized = !known.minimized;
        }
    }
    /**
     * Run an action for a chat, docking the chat in a window first when the
     * full page shows it, so the action does not replace the conversation.
     * @param {AISession} session the chat the action comes from
     * @param {object} action the action
     */
    async runAction(session, action) {
        if (this.pageSessionId === session.id) {
            this.openWindow(session.id);
        }
        try {
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(
                _t('Failed to execute UI action: %s', formatError(error)),
                {
                    type: 'danger',
                },
            );
        }
    }
    /**
     * Reload the chatter of a record, should the form on screen show it.
     * @param {string} model the model of the record
     * @param {number} id the record
     */
    reloadThread(model, id) {
        const form = this.targets.findLast((target) => target.viewType === 'form');
        form?.controller.env.bus.trigger('MAIL:RELOAD-THREAD', { model, id });
    }
    /**
     * Register a mounted view controller as the view the user looks at.
     * @param {object} target `{controller, viewType, build}`
     * @returns {Function} the unregister function
     */
    registerTarget(target) {
        this.targets.push(target);
        return () => this.targets.splice(this.targets.indexOf(target), 1);
    }
    /**
     * Describe the view on screen as the context a chat is pinned to.
     * @returns {object|null} the view context, null outside a model's view
     */
    probeContext() {
        const target = this.targets.at(-1);
        if (target) {
            return target.build();
        }
        const controller = this.action.currentController;
        const props = controller?.props || {};
        const model = props.resModel || controller?.action?.res_model;
        if (!model) {
            return null;
        }
        return props.resId
            ? { kind: 'record', model, id: props.resId }
            : { kind: 'list', model, view_type: props.type || 'list' };
    }
    /**
     * Pin a view context to a chat.
     * @param {number} id the chat
     * @param {object} [context] the context, the current view's when omitted
     * @returns {Promise<void>}
     */
    async seedContext(id, context = null) {
        const payload = context || this.probeContext();
        if (payload?.model) {
            await this.orm.silent
                .call('muk_ai.session', 'set_view_context', [id, payload])
                .catch(() => {});
        }
    }
    /**
     * Pin a view context to every chat open in a window, once per change.
     * @param {object} payload the view context
     * @returns {Promise} resolved once the last change is pinned
     */
    pushContext(payload) {
        const ids = this.windowIds;
        const key = `${ids}:${JSON.stringify(payload)}`;
        if (ids.length && payload?.model && key !== this.lastContext) {
            this.lastContext = key;
            this.pinned = Promise.all(ids.map((id) => this.seedContext(id, payload)));
        }
        return this.pinned;
    }
    /**
     * Wait briefly for a list, kanban, pivot or graph view to be on screen.
     * @returns {Promise<object|null>} its target, null when none mounts
     */
    async adjustTarget() {
        for (let waited = 0; waited <= TARGET_TIMEOUT_MS; waited += TARGET_POLL_MS) {
            const target = this.targets.at(-1);
            if (target && target.viewType !== 'form') {
                return target;
            }
            await new Promise((resolve) => setTimeout(resolve, TARGET_POLL_MS));
        }
        return null;
    }
    /**
     * Copy a text to the clipboard and say whether it worked.
     * @param {string} text the text
     */
    async copy(text) {
        try {
            await navigator.clipboard.writeText(String(text || ''));
            this.notification.add(_t('Copied to clipboard'), { type: 'success' });
        } catch {
            this.notification.add(_t('Copy failed'), { type: 'danger' });
        }
    }
}

services.add(AIChatPlugin);

registry.category('services').add('muk_ai.chat', {
    start() {
        return usePlugin(AIChatPlugin);
    },
});

/**
 * Hold the session of the chat a surface shows, following the id it reads.
 * @param {Function} getId returns the chat to show, or a falsy value
 * @returns {Function} a signal holding the `AISession`, null without a chat
 */
export function useAISession(getId) {
    const chat = usePlugin(AIChatPlugin);
    const current = signal(null);
    useEffect(() => {
        const id = getId();
        current.set(id ? untrack(() => chat.acquire(id)) : null);
        return () => id && chat.release(id);
    });
    return current;
}
