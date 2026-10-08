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
import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { registry } from '@web/core/registry';
import { user } from '@web/core/user';
import { debounce } from '@web/core/utils/timing';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { statusInfo } from '@muk_ai/core/utils/utils';

const LIMIT = 8;

/** Systray menu starting AI chats and listing the recent and unread ones. */
export class MukAISystray extends Component {
    static template = 'muk_ai.Systray';
    static components = { Dropdown, DropdownItem };
    chat = usePlugin(AIChatPlugin);
    button = signal.ref();
    state = proxy({ ids: [], loaded: false });
    statusInfo = statusInfo;
    hotkeys = isMacOS()
        ? ['Ctrl+Shift+B', 'Ctrl+Shift+F']
        : ['Alt+Shift+B', 'Alt+Shift+F'];
    setup() {
        const reload = debounce(() => this.reload(), 500, {
            leading: true,
            trailing: true,
        });
        onWillStart(() => Promise.all([this.reload(), this.chat.loadBadge()]));
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
        useHotkey('alt+shift+f', () => this.chat.openFullChat(), {
            global: true,
            bypassEditableProtection: true,
        });
    }
    /**
     * The chats this menu lists, so an extension can narrow what counts.
     * @returns {Array} a domain on `muk_ai.session`
     */
    get sessionDomain() {
        return [['user_id', '=', user.userId]];
    }
    get rows() {
        return this.state.ids.map((id) => this.chat.rows[id]).filter(Boolean);
    }
    get running() {
        return this.rows.filter((row) => ['running', 'waiting'].includes(row.state))
            .length;
    }
    /**
     * Load the unread chats first, then the most recent ones.
     */
    async reload() {
        const read = (domain) =>
            this.chat.orm.searchRead(
                'muk_ai.session',
                domain,
                ['id', 'name', 'state'],
                {
                    limit: LIMIT,
                    order: 'write_date DESC',
                },
            );
        const pages = await Promise.all([
            read([...this.sessionDomain, ['notification_unread', '=', true]]),
            read(this.sessionDomain),
        ]).catch(() => [[], []]);
        const rows = pages.flat();
        this.chat.setRows(rows);
        Object.assign(this.state, {
            ids: [...new Set(rows.map((row) => row.id))],
            loaded: true,
        });
    }
    async newChat() {
        this.chat.openWindow(await this.chat.createSession());
    }
}

registry
    .category('systray')
    .add('muk_ai.Systray', { Component: MukAISystray }, { sequence: 60 });
