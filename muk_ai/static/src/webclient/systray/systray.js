import {
    Component,
    onWillDestroy,
    onWillStart,
    proxy,
    signal,
    useListener,
    usePlugin,
} from '@odoo/owl';

import { isMacOS } from '@web/core/browser/feature_detection';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { useDropdownState } from '@web/core/dropdown/dropdown_hooks';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { debounce } from '@web/core/utils/timing';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { formatShortTimestamp, statusInfo } from '@muk_ai/core/utils/utils';
import { agentSuggestions } from '@muk_ai/chat/conversation/conversation';

/**
 * Systray menu starting AI chats, on the record on screen with its actions,
 * and listing what waits on the user, then the recent chats with a preview
 * of their last answer.
 */
export class MukAISystray extends Component {
    static template = 'muk_ai.Systray';
    static components = { Dropdown, DropdownItem };
    chat = usePlugin(AIChatPlugin);
    button = signal.ref();
    menu = useDropdownState({ onOpen: () => this.onOpened() });
    state = proxy({ ids: [], loaded: false, record: null, actions: [] });
    sessionLimit = 8;
    statusInfo = statusInfo;
    formatShortTimestamp = formatShortTimestamp;
    hotkey = isMacOS() ? 'Ctrl+Shift+B' : 'Alt+Shift+B';
    setup() {
        const reload = debounce(() => this.reload(), 500, {
            leading: true,
            trailing: true,
        });
        onWillStart(() =>
            Promise.all([this.reload(), this.chat.loadBadge(), this.chat.loadNeeds()]),
        );
        onWillDestroy(() => reload.cancel());
        useListener(this.chat.events, 'created', reload);
        useListener(this.chat.events, 'session_state', ({ detail }) => {
            if (detail.deleted) {
                this.state.ids = this.state.ids.filter(
                    (id) => id !== detail.session_id,
                );
            } else if (!this.state.ids.includes(detail.session_id)) {
                reload();
            }
        });
        useHotkey('alt+shift+b', () => this.newChat(), {
            global: true,
            bypassEditableProtection: true,
            withOverlay: () => this.button(),
        });
        useHotkey('alt+shift+f', () => this.openFullChat(), {
            global: true,
            bypassEditableProtection: true,
        });
    }
    get rows() {
        return this.state.ids.map((id) => this.chat.rows[id]).filter(Boolean);
    }
    get recent() {
        const waiting = new Set(this.chat.needs.rows.map((row) => row.session_id));
        return this.rows
            .filter((row) => !waiting.has(row.id))
            .slice(0, this.sessionLimit);
    }
    get running() {
        return this.recent.filter((row) => ['running', 'waiting'].includes(row.state))
            .length;
    }
    get recordTitle() {
        const { display_name: name } = this.state.record;
        return name ? _t('Ask about %s', name) : _t('Ask about this record');
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
    /**
     * Load the unread chats first, then the most recent ones.
     */
    async reload() {
        const read = (domain) =>
            this.chat.orm.searchRead(
                'muk_ai.session',
                domain,
                [
                    'name',
                    'state',
                    'agent_id',
                    'write_date',
                    'last_text',
                    'error_message',
                ],
                {
                    limit: this.sessionLimit,
                    order: 'write_date DESC',
                },
            );
        const pages = await Promise.all([
            read([...this.chat.chatDomain, ['notification_unread', '=', true]]),
            read(this.chat.chatDomain),
        ]).catch(() => [[], []]);
        const rows = pages.flat();
        this.chat.setRows(rows);
        Object.assign(this.state, {
            ids: [...new Set(rows.map((row) => row.id))],
            loaded: true,
        });
    }
    async onOpened() {
        this.chat.reloadNeeds();
        const context = this.chat.probeContext();
        this.state.record = context?.kind === 'record' ? context : null;
        this.state.actions = await this.loadActions();
    }
    /**
     * Return the actions offered as chips: the default agent's suggestions.
     * @returns {Promise<Array>} `{label, prompt}` entries
     */
    async loadActions() {
        await this.chat.loadAgents();
        return agentSuggestions(this.chat.agents()[0]);
    }
    async newChat() {
        this.menu.close();
        this.chat.openWindow(await this.chat.createSession());
    }
    openFullChat() {
        this.menu.close();
        return this.chat.openFullChat();
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
        const id = await this.chat.createSession();
        this.chat.openWindow(id);
        const session = this.chat.acquire(id);
        await session.ready;
        await this.runAction(session, action);
        this.chat.release(id);
    }
    /**
     * Run an offered action in a chat.
     * @param {object} session the chat
     * @param {object} action the action
     * @returns {Promise<void>}
     */
    runAction(session, action) {
        session.state.input = action.prompt;
        return session.send();
    }
    markAllRead() {
        for (const id of this.chat.badge.unreadIds) {
            this.chat.dismiss(id);
        }
    }
}

registry
    .category('systray')
    .add('muk_ai.Systray', { Component: MukAISystray }, { sequence: 28 });
