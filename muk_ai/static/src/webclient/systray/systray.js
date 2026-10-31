// @odoo-module

import { Component, onWillStart, onWillUnmount, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { isMacOS } from '@web/core/browser/feature_detection';
import { debounce } from '@web/core/utils/timing';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

import { busSubscribe, busUnsubscribe } from '@muk_ai/core/compat/bus';
import {
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
        this.bus = this.env.services.bus_service;
        this.action = useService('action');
        this.notification = useService('notification');
        this.chatWindow = useService('muk_ai.chat_window');
        this.sessionLimit = 8;
        this.state = useState({
            sessions: [],
            loaded: false,
            record: null,
            actions: [],
        });
        this.needs = useState({ rows: [], busy: {} });
        this.badge = useNotificationBadge();
        this._busHandler = null;
        this._loadSeq = 0;
        this._needsSeq = 0;
        this._debouncedLoad = debounce(() => this._load(), 500, {
            leading: true,
            trailing: true,
        });
        this.reloadNeeds = debounce(() => this._fetchNeeds(), 300, {
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
            await Promise.all([this._load(), this._fetchNeeds()]);
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
        try {
            const domain = chatLists.domain;
            const fields = [
                'id',
                'name',
                'state',
                'agent_id',
                'write_date',
                'last_text',
                'error_message',
            ];
            const options = { limit: this.sessionLimit, order: 'write_date DESC' };
            const [recent, unread] = await Promise.all([
                this.orm.searchRead('muk_ai.session', domain, fields, options),
                this.orm.searchRead(
                    'muk_ai.session',
                    [...domain, ['notification_unread', '=', true]],
                    fields,
                    options,
                ),
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
    /**
     * Read what waits on the user, keeping only the answer of the last read.
     */
    async _fetchNeeds() {
        const seq = ++this._needsSeq;
        const rows = await this.orm.silent
            .call('muk_ai.session', 'get_needs_you', [])
            .catch(() => null);
        if (rows && seq === this._needsSeq) {
            this.needs.rows = rows;
        }
    }
    _connectBus() {
        this._busHandler = (payload) => this._onBusEvent(payload);
        this._activityHandler = () => this.reloadNeeds();
        busSubscribe(this.bus, 'muk_ai.session_state', this._busHandler);
        busSubscribe(this.bus, 'mail.activity/updated', this._activityHandler);
    }
    _disconnectBus() {
        if (this._busHandler) {
            busUnsubscribe(this.bus, 'muk_ai.session_state', this._busHandler);
            busUnsubscribe(this.bus, 'mail.activity/updated', this._activityHandler);
            this._busHandler = null;
        }
    }
    _onBusEvent(payload) {
        if (!payload || !payload.session_id) return;
        if (
            payload.deleted ||
            payload.awaiting_user ||
            this.needs.rows.some((row) => row.session_id === payload.session_id)
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
        for (const key of ['state', 'name', 'last_text', 'error_message']) {
            if (payload[key]) {
                updated[key] = payload[key];
            }
        }
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
    }
    get recent() {
        const waiting = new Set(this.needs.rows.map((row) => row.session_id));
        return this.state.sessions
            .filter((row) => !waiting.has(row.id))
            .slice(0, this.sessionLimit);
    }
    get runningCount() {
        return this.recent.filter((s) => ['running', 'waiting'].includes(s.state))
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
        const count = this.needs.rows.length;
        return count === 1 ? _t('1 thing needs you') : _t('%s things need you', count);
    }
    get buttonTitle() {
        return this.needs.rows.length ? `MuK AI - ${this.needsTitle}` : 'MuK AI';
    }
    get recordTitle() {
        const name = this.state.record?.display_name;
        return name ? _t('Ask about %s', name) : _t('Ask about this record');
    }
    statusDotClass(state) {
        return statusBadgeClass(state);
    }
    formatShortTimestamp(at) {
        return formatShortTimestamp(at);
    }
    /**
     * Return the image of an agent.
     * @param {number} agentId the agent
     * @returns {string} the image route
     */
    agentImage(agentId) {
        return `/web/image/muk_ai.agent/${agentId || 0}/image_128`;
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
        this._agents ||= this.orm.searchRead(
            'muk_ai.agent',
            [['active', '=', true]],
            ['id', 'name', 'description', 'suggestions'],
            { order: 'sequence, name' },
        );
        const agents = await this._agents.catch(() => []);
        return agentSuggestions({ agents });
    }
    async _createSession() {
        const [id] = await this.orm.create('muk_ai.session', [
            { name: _t('New Chat') },
        ]);
        return id;
    }
    async onNewChat() {
        this.chatWindow.open(await this._createSession());
        await this._load();
    }
    /**
     * Open a new chat to pick from every action, not only the offered ones.
     * @returns {Promise<void>}
     */
    more() {
        return this.onNewChat();
    }
    /**
     * Start a chat on what is on screen, run an action in it and show it.
     * @param {object} action one of the offered actions
     */
    async start(action) {
        const id = await this._createSession();
        await seedSessionContext(this.env, id);
        await this.runAction(id, action);
        this.chatWindow.open(id);
    }
    /**
     * Run an offered action in a chat.
     * @param {number} sessionId the chat
     * @param {object} action the action
     * @returns {Promise<object>} the chat's snapshot
     */
    runAction(sessionId, action) {
        return this.orm.call('muk_ai.session', 'start', [[sessionId], action.prompt]);
    }
    onOpenSession(session) {
        this.chatWindow.open(session.id);
    }
    async onOpenFullChat() {
        await this.action.doAction({
            type: 'ir.actions.client',
            tag: 'muk_ai.chat',
        });
    }
    /**
     * Approve or reject a waiting item in place through the method it names.
     * @param {object} row the item, as `get_needs_you` returns it
     * @param {string} verb `approve` or `reject`
     */
    async decideNeed(row, verb) {
        this.needs.busy[row.key] = true;
        try {
            await this.orm.call(row.res_model, row[verb], [[row.res_id]]);
            this.needs.rows = this.needs.rows.filter((item) => item.key !== row.key);
        } catch (error) {
            this.notification.add(formatError(error), { type: 'danger' });
        } finally {
            delete this.needs.busy[row.key];
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
    markAllRead() {
        return this.orm.call('muk_ai.session', 'dismiss_notifications', [
            [...this.badge.unreadIds],
        ]);
    }
}

registry
    .category('systray')
    .add('muk_ai.Systray', { Component: MukAISystray }, { sequence: 60 });
