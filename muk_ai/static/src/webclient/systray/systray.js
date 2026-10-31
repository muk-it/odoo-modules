// @odoo-module

import { Component, onWillStart, onWillUnmount, useRef, useState } from '@odoo/owl';

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { isMacOS } from '@web/core/browser/feature_detection';
import { debounce } from '@web/core/utils/timing';
import { Dropdown } from '@web/core/dropdown/dropdown';
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
import { busSubscribe, busUnsubscribe } from '@muk_ai/core/compat/bus';
import { probeCurrentView, seedSessionContext } from '@muk_ai/views/context';

const NEW_CHAT_HOTKEY = 'alt+shift+b';
const FULL_CHAT_HOTKEY = 'alt+shift+f';
const SESSION_FIELDS = [
    'name',
    'state',
    'agent_id',
    'write_date',
    'last_text',
    'error_message',
];

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
        this.bus = this.env.services.bus_service;
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
        this.badge = useNotificationBadge();
        this.sessionLimit = 8;
        this.hotkey = isMacOS() ? 'Ctrl+Shift+B' : 'Alt+Shift+B';
        this.agentImage = agentImage;
        this.formatShortTimestamp = formatShortTimestamp;
        this.statusBadgeClass = statusBadgeClass;
        this._loadSeq = 0;
        this._needsSeq = 0;
        this._debouncedLoad = debounce(() => this._load(), 500, {
            leading: true,
            trailing: true,
        });
        this.reloadNeeds = debounce(() => this.fetchNeeds(), 300, {
            leading: true,
            trailing: true,
        });
        this._onSessionState = (payload) => this._onBusEvent(payload);
        this._onActivity = () => this.reloadNeeds();
        this.btnRef = useRef('systrayBtn');
        useHotkey(NEW_CHAT_HOTKEY, () => this.newChat(), {
            global: true,
            bypassEditableProtection: true,
            withOverlay: () => this.btnRef.el,
        });
        useHotkey(FULL_CHAT_HOTKEY, () => this.openFullChat(), {
            global: true,
            bypassEditableProtection: true,
        });
        onWillStart(async () => {
            await Promise.all([this._load(), this.fetchNeeds()]);
            busSubscribe(this.bus, 'muk_ai.session_state', this._onSessionState);
            busSubscribe(this.bus, 'mail.activity/updated', this._onActivity);
        });
        onWillUnmount(() => {
            busUnsubscribe(this.bus, 'muk_ai.session_state', this._onSessionState);
            busUnsubscribe(this.bus, 'mail.activity/updated', this._onActivity);
            this._debouncedLoad.cancel();
            this.reloadNeeds.cancel();
        });
    }
    get recent() {
        const waiting = new Set(this.state.needs.map((need) => need.session_id));
        return this.state.sessions
            .filter((row) => !waiting.has(row.id))
            .slice(0, this.sessionLimit);
    }
    get running() {
        return this.recent.filter((row) => ['running', 'waiting'].includes(row.state))
            .length;
    }
    get badgeLabel() {
        return this.badge.count > 99 ? '99+' : String(this.badge.count);
    }
    get needsTitle() {
        const count = this.state.needs.length;
        return count === 1 ? _t('1 thing needs you') : _t('%s things need you', count);
    }
    get recordTitle() {
        const name = this.state.record.display_name;
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
    /**
     * Load the unread chats first, then the most recent ones.
     */
    async _load() {
        const seq = ++this._loadSeq;
        const domain = chatLists.domain;
        const options = { limit: this.sessionLimit, order: 'write_date DESC' };
        try {
            const [recent, unread] = await Promise.all([
                this.orm.searchRead('muk_ai.session', domain, SESSION_FIELDS, options),
                this.orm.searchRead(
                    'muk_ai.session',
                    [...domain, ['notification_unread', '=', true]],
                    SESSION_FIELDS,
                    options,
                ),
            ]);
            if (seq === this._loadSeq) {
                const seen = new Set(unread.map((row) => row.id));
                this.state.sessions = [
                    ...unread,
                    ...recent.filter((row) => !seen.has(row.id)),
                ];
            }
        } catch {
            if (seq === this._loadSeq) {
                this.state.sessions = [];
            }
        }
        this.state.loaded = true;
    }
    /**
     * Read what waits on the user, keeping only the answer of the last read.
     */
    async fetchNeeds() {
        const seq = ++this._needsSeq;
        const rows = await this.orm.silent
            .call('muk_ai.session', 'get_needs_you', [])
            .catch(() => null);
        if (rows && seq === this._needsSeq) {
            this.state.needs = rows;
        }
    }
    _onBusEvent(payload) {
        if (!payload || !payload.session_id) {
            return;
        }
        const id = payload.session_id;
        if (
            payload.deleted ||
            payload.awaiting_user ||
            this.state.needs.some((need) => need.session_id === id)
        ) {
            this.reloadNeeds();
        }
        if (payload.deleted) {
            this.state.sessions = this.state.sessions.filter((row) => row.id !== id);
            return;
        }
        const row = this.state.sessions.find((entry) => entry.id === id);
        if (!row || payload.state === 'done') {
            this._debouncedLoad();
            return;
        }
        if (payload.state) {
            row.state = payload.state;
        }
        if (payload.name) {
            row.name = payload.name;
        }
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
        const [agent] = await this.orm.searchRead(
            'muk_ai.agent',
            [['active', '=', true]],
            ['suggestions'],
            { order: 'sequence, name', limit: 1 },
        );
        return agentSuggestions(agent);
    }
    /**
     * Create a chat on what the user looks at.
     * @returns {Promise<number>} the new chat
     */
    async createSession() {
        const [id] = await this.orm.create('muk_ai.session', [
            { name: _t('New Chat') },
        ]);
        await seedSessionContext(this.env, id);
        this._debouncedLoad();
        return id;
    }
    async newChat() {
        this.chatWindow.open(await this.createSession());
    }
    openFullChat() {
        return this.action.doAction({ type: 'ir.actions.client', tag: 'muk_ai.chat' });
    }
    /**
     * Open a new chat to pick from every action, not only the offered ones.
     * @returns {Promise<void>}
     */
    more() {
        return this.newChat();
    }
    /**
     * Start a chat in a window and run an action in it.
     * @param {object} action one of the offered actions
     */
    async start(action) {
        const id = await this.createSession();
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
     * @returns {Promise<object>} the snapshot of the chat
     */
    runAction(sessionId, action) {
        return this.orm.call('muk_ai.session', 'start', [sessionId, action.prompt]);
    }
    /**
     * Approve or reject a waiting item in place through the method it names.
     * @param {object} need the item, as `get_needs_you` returns it
     * @param {string} verb `approve` or `reject`
     */
    async decideNeed(need, verb) {
        this.state.busy[need.key] = true;
        try {
            await this.orm.call(need.res_model, need[verb], [[need.res_id]]);
            this.state.needs = this.state.needs.filter((row) => row.key !== need.key);
        } catch (error) {
            this.notification.add(formatError(error), { type: 'danger' });
        } finally {
            delete this.state.busy[need.key];
            this.reloadNeeds();
        }
    }
    /**
     * Open a waiting item: a chat in a window, anything else through the
     * action its `open` method returns.
     * @param {object} need the item, as `get_needs_you` returns it
     * @returns {Promise<void>}
     */
    async openNeed(need) {
        if (need.session_id) {
            this.chatWindow.open(need.session_id);
            return;
        }
        const action = await this.orm.call(need.res_model, need.open, [[need.res_id]]);
        await this.action.doAction(action);
    }
    markAllRead() {
        return this.orm.call('muk_ai.session', 'dismiss_notifications', [
            this.badge.unreadIds,
        ]);
    }
}

registry
    .category('systray')
    .add('muk_ai.Systray', { Component: MukAISystray }, { sequence: 60 });
