import { Component, onWillStart, onWillUnmount, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { user } from '@web/core/user';
import { useService } from '@web/core/utils/hooks';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { isMacOS } from '@web/core/browser/feature_detection';
import { debounce } from '@web/core/utils/timing';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

import { useNotificationBadge } from '@muk_ai/core/notification_badge';

const SYSTRAY_LIMIT = 8;
const NEW_CHAT_HOTKEY = 'alt+shift+b';
const FULL_CHAT_HOTKEY = 'alt+shift+f';

/** Systray dropdown for launching AI chat windows and recent sessions. */
export class MukAISystray extends Component {
    static template = 'muk_ai.Systray';
    static components = { Dropdown, DropdownItem };
    static props = {};
    setup() {
        this.orm = useService('orm');
        this.bus = useService('bus_service');
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');
        this.state = useState({
            sessions: [],
            loaded: false,
        });
        this.badge = useNotificationBadge();
        this._busHandler = null;
        this._loadSeq = 0;
        this._debouncedLoad = debounce(() => this._load(), 500, {
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
            await this._load();
            this._connectBus();
        });
        onWillUnmount(() => {
            this._disconnectBus();
            this._debouncedLoad.cancel();
        });
    }
    async _load() {
        const seq = ++this._loadSeq;
        try {
            const [recent, unread] = await Promise.all([
                this.orm.searchRead(
                    'muk_ai.session',
                    [['user_id', '=', user.userId]],
                    ['id', 'name', 'state'],
                    { limit: SYSTRAY_LIMIT, order: 'create_date DESC' },
                ),
                this.orm.searchRead(
                    'muk_ai.session',
                    [
                        ['user_id', '=', user.userId],
                        ['notification_unread', '=', true],
                    ],
                    ['id', 'name', 'state'],
                    { limit: SYSTRAY_LIMIT, order: 'create_date DESC' },
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
    _connectBus() {
        this._busHandler = (payload) => this._onBusEvent(payload);
        this.bus.subscribe('muk_ai.session_state', this._busHandler);
    }
    _disconnectBus() {
        if (this._busHandler) {
            this.bus.unsubscribe('muk_ai.session_state', this._busHandler);
            this._busHandler = null;
        }
    }
    _onBusEvent(payload) {
        if (!payload || !payload.session_id) return;
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
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
    }
    get runningCount() {
        return this.state.sessions.filter(
            (s) => s.state === 'running' || s.state === 'waiting',
        ).length;
    }
    get hasRunning() {
        return this.runningCount > 0;
    }
    get badgeLabel() {
        return this.badge.count > 99 ? '99+' : String(this.badge.count);
    }
    get newChatHotkeyLabel() {
        return isMacOS() ? 'Ctrl+Shift+B' : 'Alt+Shift+B';
    }
    get fullChatHotkeyLabel() {
        return isMacOS() ? 'Ctrl+Shift+F' : 'Alt+Shift+F';
    }
    statusDotClass(state) {
        return (
            {
                new: 'mk_state_new',
                running: 'mk_state_running',
                waiting: 'mk_state_waiting',
                done: 'mk_state_done',
                error: 'mk_state_error',
                stopped: 'mk_state_stopped',
            }[state] || 'mk_state_new'
        );
    }
    async onNewChat() {
        const name = _t('Chat %s', new Date().toLocaleString());
        const sessionId = await this.orm.create('muk_ai.session', [{ name }]);
        const id = Array.isArray(sessionId) ? sessionId[0] : sessionId;
        this.chatWindow.open(id);
        await this._load();
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
}

registry
    .category('systray')
    .add('muk_ai.Systray', { Component: MukAISystray }, { sequence: 60 });
