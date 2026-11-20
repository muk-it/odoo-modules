import { Chatter } from '@mail/chatter/web_portal/chatter';
import { Message } from '@mail/core/common/message';
import { messageActionsRegistry } from '@mail/core/common/message_actions';

import { reactive, useState } from '@odoo/owl';

import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';
import { patch } from '@web/core/utils/patch';

import '@mail/chatter/web/chatter_patch';

/**
 * @param {import("models").Message} message
 * @returns {boolean} whether the message can move to another record
 */
export function isMovable(message) {
    return !message.trackingValues.length && !message.is_transient;
}

/** The messages of a chatter picked to move to another record. */
export class MessageMoveSelection {
    active = false;
    ids = new Set();
    anchor = null;
    constructor({ onStart }) {
        this.onStart = onStart;
    }
    has(message) {
        return this.ids.has(message.id);
    }
    start(message) {
        this.ids.clear();
        this.ids.add(message.id);
        this.anchor = message.id;
        this.active = true;
        this.onStart();
    }
    stop() {
        this.ids.clear();
        this.active = false;
    }
    /**
     * Select or unselect a message, or with ``extend`` every message up to the last one clicked.
     *
     * @param {import("models").Message} message
     * @param {import("models").Thread} thread
     * @param {boolean} extend
     */
    toggle(message, thread, extend) {
        const movable = thread.messages.filter(isMovable);
        const from = movable.findIndex((m) => m.id === this.anchor);
        const to = movable.findIndex((m) => m.id === message.id);
        if (extend && from !== -1) {
            for (const m of movable.slice(Math.min(from, to), Math.max(from, to) + 1)) {
                this.ids.add(m.id);
            }
        } else if (this.has(message)) {
            this.ids.delete(message.id);
        } else {
            this.ids.add(message.id);
        }
        this.anchor = message.id;
    }
}

Object.assign(Chatter.components, { DropdownItem });

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.action = useService('action');
        this.moveState = useState({ configurations: [] });
        useHotkey('escape', () => this.messageMove.stop(), {
            isAvailable: () => this.messageMove.active,
        });
    },
    get childSubEnv() {
        const res = super.childSubEnv;
        this.messageMove ??= reactive(
            new MessageMoveSelection({
                onStart: () => {
                    this.state.composerType = false;
                    this.closeSearch();
                    this.orm
                        .call('mail.message', 'get_route_configurations', [])
                        .then((configurations) => {
                            this.moveState.configurations = configurations;
                        });
                },
            }),
        );
        res.inChatter.messageMove = this.messageMove;
        return res;
    },
    get moveCountLabel() {
        const count = this.state.messageMove.ids.size;
        return count === 1 ? _t('1 selected') : _t('%(count)s selected', { count });
    },
    changeThread() {
        super.changeThread(...arguments);
        this.messageMove?.stop();
    },
    /**
     * Open the router for the selected messages, preset with a routing rule if given.
     *
     * @param {number} [configurationId]
     */
    async onClickMoveSelected(configurationId) {
        const thread = this.state.thread;
        const ids = thread.messages
            .filter((m) => this.messageMove.has(m))
            .map((m) => m.id);
        await this.action.doAction(
            await this.orm.call('mail.message', 'action_route_message', [ids]),
            {
                additionalContext: {
                    default_configuration_id: configurationId,
                    mail_route_single_record: true,
                },
                onClose: () => {
                    thread.messages.splice(0, thread.messages.length);
                    thread.fetchNewMessages();
                },
            },
        );
    },
});

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.env.inChatter?.messageMove) {
            this.messageMove = useState(this.env.inChatter.messageMove);
        }
    },
    get attClass() {
        if (!this.messageMove?.active) {
            return super.attClass;
        }
        const movable = isMovable(this.message);
        return {
            ...super.attClass,
            mk_move_selectable: movable,
            mk_move_selected: movable && this.messageMove.has(this.message),
            mk_move_disabled: !movable,
        };
    },
    async onClick(ev) {
        if (!this.messageMove?.active) {
            return super.onClick(ev);
        }
        if (isMovable(this.message)) {
            this.messageMove.toggle(this.message, this.props.thread, ev.shiftKey);
        }
    },
});

messageActionsRegistry.add('muk-move', {
    condition: (component) =>
        Boolean(component.env.inChatter?.messageMove) &&
        component.props.thread?.model !== 'discuss.channel' &&
        component.store.self.isInternalUser &&
        isMovable(component.props.message),
    icon: 'fa fa-exchange',
    title: _t('Move'),
    onClick: (component) =>
        component.env.inChatter.messageMove.start(component.props.message),
    sequence: 36,
});
