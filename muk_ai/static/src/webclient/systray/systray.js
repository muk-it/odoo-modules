import { Component, onWillStart, onWillUnmount, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { isMacOS } from '@web/core/browser/feature_detection';
import { debounce } from '@web/core/utils/timing';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { useDropdownState } from '@web/core/dropdown/dropdown_hooks';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

import {
    agentImage,
    agentSuggestions,
    chatLists,
    formatError,
    formatShortTimestamp,
    statusBadgeClass,
} from '@muk_ai/chat/utils';
import { useNotificationBadge } from '@muk_ai/core/notification_badge';
import { probeCurrentView, seedSessionContext } from '@muk_ai/views/context';

const NEW_CHAT_HOTKEY = 'alt+shift+b';
const FULL_CHAT_HOTKEY = 'alt+shift+f';

/**
 * Systray menu starting AI chats, on the record on screen with its actions,
 * and listing what waits on the user, then the recent chats with a preview
 * of their last answer.
 */
export class MukAISystray extends Component {
    static template = 'muk_ai.Systray';
    static components = { Dropdown, DropdownItem };
    static props = {};
    setup() {
        this.orm = useService('orm');
        this.bus = useService('bus_service');
        this.action = useService('action');
        this.notification = useService('notification');
        this.chatWindow = useService('muk_ai.chat_window');
        this.state = useState({
            sessions: [],
            loaded: false,
            record: null,
            actions: [],
            needs: [],
            busy: {},
        });
        this.menu = useDropdownState({ onOpen: () => this.onOpened() });
        this.badge = useNotificationBadge();
        this.sessionLimit = 8;
        this.agentImage = agentImage;
        this.formatShortTimestamp = formatShortTimestamp;
        this.statusDotClass = statusBadgeClass;
        this._busHandlers = {};
        this._loadSeq = 0;
        this._needsSeq = 0;
        this._debouncedLoad = debounce(() => this._load(), 500, {
            leading: true,
            trailing: true,
        });
        this.reloadNeeds = debounce(() => this._loadNeeds(), 300, {
            leading: true,
            trailing: true,
        });
        this.btnRef = useRef('systrayBtn');
        useHotkey(NEW_CHAT_HOTKEY, () => this.onNewChat(), {
            global: true,
            bypassEditableProtection: true,
            withOverlay: () => this.btnRef.el,
        });
        useHotkey(FULL_CHAT_HOTKEY, () => this.onOpenFullChat(), {
            global: true,
            bypassEditableProtection: true,
        });
        onWillStart(async () => {
            await Promise.all([this._load(), this._loadNeeds()]);
            this._connectBus();
        });
        onWillUnmount(() => {
            this._disconnectBus();
            this._debouncedLoad.cancel();
            this.reloadNeeds.cancel();
        });
    }
    async _load() {
        const seq = ++this._loadSeq;
        const fields = [
            'id',
            'name',
            'state',
            'agent_id',
            'write_date',
            'last_text',
            'error_message',
        ];
        const read = (domain) =>
            this.orm.searchRead('muk_ai.session', domain, fields, {
                limit: this.sessionLimit,
                order: 'write_date DESC',
            });
        try {
            const [recent, unread] = await Promise.all([
                read(chatLists.domain),
                read([...chatLists.domain, ['notification_unread', '=', true]]),
            ]);
            if (seq === this._loadSeq) {
                this.state.sessions = this._mergeUnreadFirst(unread, recent);
            }
        } catch {
            if (seq === this._loadSeq) {
                this.state.sessions = [];
            }
        }
        this.state.loaded = true;
    }
    async _loadNeeds() {
        const seq = ++this._needsSeq;
        const rows = await this.orm.silent
            .call('muk_ai.session', 'get_needs_you', [])
            .catch(() => null);
        if (rows && seq === this._needsSeq) {
            this.state.needs = rows;
        }
    }
    _mergeUnreadFirst(unread, recent) {
        const merged = [...unread];
        const seen = new Set(unread.map((s) => s.id));
        for (const session of recent) {
            if (!seen.has(session.id)) {
                seen.add(session.id);
                merged.push(session);
            }
        }
        return merged;
    }
    _connectBus() {
        this._busHandlers = {
            'muk_ai.session_state': (payload) => this._onBusEvent(payload),
            'mail.activity/updated': () => this.reloadNeeds(),
        };
        for (const [name, handler] of Object.entries(this._busHandlers)) {
            this.bus.subscribe(name, handler);
        }
    }
    _disconnectBus() {
        for (const [name, handler] of Object.entries(this._busHandlers)) {
            this.bus.unsubscribe(name, handler);
        }
        this._busHandlers = {};
    }
    _onBusEvent(payload) {
        if (!payload || !payload.session_id) return;
        if (
            payload.deleted ||
            payload.awaiting_user ||
            this.state.needs.some((row) => row.session_id === payload.session_id)
        ) {
            this.reloadNeeds();
        }
        if (payload.deleted) {
            this.state.sessions = this.state.sessions.filter(
                (s) => s.id !== payload.session_id,
            );
            return;
        }
        const idx = this.state.sessions.findIndex((s) => s.id === payload.session_id);
        if (idx < 0) {
            this._debouncedLoad();
            return;
        }
        const updated = { ...this.state.sessions[idx] };
        if (payload.state) updated.state = payload.state;
        if (payload.name) updated.name = payload.name;
        if (payload.state && payload.state !== 'running') {
            this._debouncedLoad();
        }
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
    }
    get recent() {
        const waiting = new Set(this.state.needs.map((row) => row.session_id));
        return this.state.sessions
            .filter((s) => !waiting.has(s.id))
            .slice(0, this.sessionLimit);
    }
    get runningCount() {
        return this.recent.filter((s) => s.state === 'running' || s.state === 'waiting')
            .length;
    }
    get hasRunning() {
        return this.runningCount > 0;
    }
    get badgeLabel() {
        return this.badge.count > 99 ? '99+' : String(this.badge.count);
    }
    get hotkeyLabel() {
        return isMacOS() ? 'Ctrl+Shift+B' : 'Alt+Shift+B';
    }
    get needsTitle() {
        const count = this.state.needs.length;
        return count === 1 ? _t('1 thing needs you') : _t('%s things need you', count);
    }
    get buttonTitle() {
        return this.state.needs.length ? `MuK AI - ${this.needsTitle}` : 'MuK AI';
    }
    get recordTitle() {
        const name = this.state.record?.display_name;
        return name ? _t('Ask about %s', name) : _t('Ask about this record');
    }
    /**
     * Return the line under a chat: its error, its progress or its last answer.
     * @param {object} row the chat
     * @returns {string} plain text
     */
    preview(row) {
        if (row.state === 'error') {
            return row.error_message || '';
        }
        if (row.state === 'running') {
            return _t('Working...');
        }
        return (row.last_text || '')
            .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
            .replace(/[*_`#>|]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }
    async onOpened() {
        this.reloadNeeds();
        const context = await probeCurrentView(this.env);
        this.state.record = context?.kind === 'record' ? context : null;
        this.state.actions = await this.loadActions();
    }
    /**
     * Return the actions offered as chips: the default agent's suggestions.
     * @returns {Promise<Array>} `{label, prompt}` entries
     */
    async loadActions() {
        const agents = await this.orm
            .searchRead('muk_ai.agent', [['active', '=', true]], ['suggestions'], {
                order: 'sequence, name',
                limit: 1,
            })
            .catch(() => []);
        return agentSuggestions({ agents });
    }
    async createSession() {
        const [id] = await this.orm.create('muk_ai.session', [
            { name: _t('New Chat') },
        ]);
        return id;
    }
    async onNewChat() {
        this.menu.close();
        this.chatWindow.open(await this.createSession());
        await this._load();
    }
    onOpenSession(session) {
        this.chatWindow.open(session.id);
    }
    async onOpenFullChat() {
        this.menu.close();
        await this.action.doAction({
            type: 'ir.actions.client',
            tag: 'muk_ai.chat',
        });
    }
    /**
     * Open a new chat to pick from every action, not only the offered ones.
     * @returns {Promise<void>}
     */
    more() {
        return this.onNewChat();
    }
    /**
     * Start a chat in a window and run an action in it.
     * @param {object} action one of the offered actions
     */
    async start(action) {
        const id = await this.createSession();
        await seedSessionContext(this.env, id);
        try {
            await this.runAction(id, action);
        } catch (error) {
            this.notification.add(formatError(error), { type: 'danger' });
        }
        this.chatWindow.open(id);
    }
    /**
     * Run an offered action in a chat.
     * @param {number} sessionId the chat
     * @param {object} action the action
     * @returns {Promise<object>} the chat snapshot
     */
    runAction(sessionId, action) {
        return this.orm.call('muk_ai.session', 'start', [sessionId, action.prompt]);
    }
    markAllRead() {
        return this.orm.call('muk_ai.session', 'dismiss_notifications', [
            this.badge.unreadIds,
        ]);
    }
    /**
     * Approve or reject a waiting item in place through the method it names.
     * @param {object} row the item, as `get_needs_you` returns it
     * @param {string} verb `approve` or `reject`
     */
    async decideNeed(row, verb) {
        this.state.busy[row.key] = true;
        try {
            await this.orm.call(row.res_model, row[verb], [[row.res_id]]);
            this.state.needs = this.state.needs.filter((item) => item.key !== row.key);
        } catch (error) {
            this.notification.add(formatError(error), { type: 'danger' });
        } finally {
            delete this.state.busy[row.key];
            this.reloadNeeds();
        }
    }
    /**
     * Open a waiting item: a chat in a window, anything else through the
     * action its `open` method returns.
     * @param {object} row the item, as `get_needs_you` returns it
     */
    async openNeed(row) {
        if (row.session_id) {
            this.chatWindow.open(row.session_id);
            return;
        }
        const action = await this.orm.call(row.res_model, row.open, [[row.res_id]]);
        await this.action.doAction(action);
    }
}

registry
    .category('systray')
    .add('muk_ai.Systray', { Component: MukAISystray }, { sequence: 60 });
