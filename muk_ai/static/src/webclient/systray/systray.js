import { Component, onWillStart, onWillUnmount, useRef, useState } from '@odoo/owl';

import { isMacOS } from '@web/core/browser/feature_detection';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { useDropdownState } from '@web/core/dropdown/dropdown_hooks';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { debounce } from '@web/core/utils/timing';

import {
    agentImage,
    agentSuggestions,
    chatLists,
    formatError,
    formatShortTimestamp,
} from '@muk_ai/chat/utils';
import { useNotificationBadge } from '@muk_ai/core/notification_badge';
import { probeCurrentView, seedSessionContext } from '@muk_ai/views/context';

const NEEDS_ICONS = { back_hand: 'fa-hand-paper-o', question_mark: 'fa-question' };
const STATE_CLASSES = {
    running: 'mk_state_running',
    waiting: 'mk_state_waiting',
    error: 'mk_state_error',
};

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
        this.badge = useNotificationBadge();
        this.menu = useDropdownState({ onOpen: () => this.onOpened() });
        this.state = useState({
            sessions: [],
            loaded: false,
            needs: [],
            busy: {},
            record: null,
            actions: [],
        });
        this.sessionLimit = 8;
        this.hotkey = isMacOS() ? 'Ctrl+Shift+B' : 'Alt+Shift+B';
        this.formatShortTimestamp = formatShortTimestamp;
        this.agentImage = agentImage;
        this.button = useRef('systrayBtn');
        this.loadSeq = 0;
        this.needsSeq = 0;
        this.reloadSessions = debounce(() => this.load(), 500, {
            leading: true,
            trailing: true,
        });
        this.reloadNeeds = debounce(() => this.loadNeeds(), 300, {
            leading: true,
            trailing: true,
        });
        const onSessionState = (payload) => this.onSessionState(payload);
        const onActivity = () => this.reloadNeeds();
        useHotkey('alt+shift+b', () => this.newChat(), {
            global: true,
            bypassEditableProtection: true,
            withOverlay: () => this.button.el,
        });
        useHotkey('alt+shift+f', () => this.openFullChat(), {
            global: true,
            bypassEditableProtection: true,
        });
        onWillStart(async () => {
            await Promise.all([this.load(), this.loadNeeds()]);
            this.bus.subscribe('muk_ai.session_state', onSessionState);
            this.bus.subscribe('mail.activity/updated', onActivity);
        });
        onWillUnmount(() => {
            this.bus.unsubscribe('muk_ai.session_state', onSessionState);
            this.bus.unsubscribe('mail.activity/updated', onActivity);
            this.reloadSessions.cancel();
            this.reloadNeeds.cancel();
        });
    }
    get recent() {
        const waiting = new Set(this.state.needs.map((row) => row.session_id));
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
     * Return the icon class of a waiting item.
     * @param {string} icon the icon the item names
     * @returns {string} a Font Awesome class
     */
    needIcon(icon) {
        return (
            NEEDS_ICONS[icon] || (icon?.startsWith('fa-') ? icon : 'fa-hand-paper-o')
        );
    }
    stateClass(state) {
        return STATE_CLASSES[state] || '';
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
    async load() {
        const seq = ++this.loadSeq;
        const domain = chatLists.domain;
        const fields = [
            'name',
            'state',
            'agent_id',
            'write_date',
            'last_text',
            'error_message',
        ];
        const read = (extra) =>
            this.orm.searchRead('muk_ai.session', [...domain, ...extra], fields, {
                limit: this.sessionLimit,
                order: 'write_date DESC',
            });
        try {
            const [unread, recent] = await Promise.all([
                read([['notification_unread', '=', true]]),
                read([]),
            ]);
            if (seq === this.loadSeq) {
                const seen = new Set(unread.map((row) => row.id));
                this.state.sessions = [
                    ...unread,
                    ...recent.filter((row) => !seen.has(row.id)),
                ];
            }
        } catch {
            if (seq === this.loadSeq) {
                this.state.sessions = [];
            }
        }
        this.state.loaded = true;
    }
    /**
     * Read what waits on the user, keeping only the answer of the last read.
     */
    async loadNeeds() {
        const seq = ++this.needsSeq;
        const rows = await this.orm.silent
            .call('muk_ai.session', 'get_needs_you', [])
            .catch(() => null);
        if (rows && seq === this.needsSeq) {
            this.state.needs = rows;
        }
    }
    onSessionState(payload) {
        if (!payload?.session_id) {
            return;
        }
        const id = payload.session_id;
        if (
            payload.deleted ||
            payload.awaiting_user ||
            this.state.needs.some((row) => row.session_id === id)
        ) {
            this.reloadNeeds();
        }
        if (payload.deleted) {
            this.state.sessions = this.state.sessions.filter((row) => row.id !== id);
            return;
        }
        const row = this.state.sessions.find((session) => session.id === id);
        if (!row) {
            this.reloadSessions();
            return;
        }
        for (const key of ['state', 'name', 'last_text', 'error_message']) {
            if (payload[key] !== undefined) {
                row[key] = payload[key];
            }
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
     * @returns {Promise<Array>} `{label, preview, prompt}` entries
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
     * Create a new chat.
     * @returns {Promise<number>} the chat
     */
    async createSession() {
        const [id] = await this.orm.create('muk_ai.session', [
            { name: _t('New Chat') },
        ]);
        return id;
    }
    async newChat() {
        this.menu.close();
        this.chatWindow.open(await this.createSession());
    }
    openFullChat() {
        this.menu.close();
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
        await seedSessionContext(this.env, id);
        await this.runAction(id, action);
        this.chatWindow.open(id);
    }
    /**
     * Run an offered action in a chat.
     * @param {number} sessionId the chat
     * @param {object} action the action
     * @returns {Promise}
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
