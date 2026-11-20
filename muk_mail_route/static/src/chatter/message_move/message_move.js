import { Chatter } from '@mail/chatter/web_portal_project/chatter';
import { Message } from '@mail/core/common/message';
import { registerMessageAction } from '@mail/core/common/message_actions';

import { signal, t } from '@odoo/owl';

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
    return message.message_type !== 'tracking' && !message.is_transient;
}

/** The messages of a chatter picked to move to another record. */
export class MessageMoveSelection {
    active = signal(false);
    ids = signal.Set(new Set(), { type: t.number() });
    anchor = null;
    constructor({ onStart }) {
        this.onStart = onStart;
    }
    has(message) {
        return this.ids().has(message.id);
    }
    start(message) {
        this.ids().clear();
        this.ids().add(message.id);
        this.anchor = message.id;
        this.active.set(true);
        this.onStart();
    }
    stop() {
        this.ids().clear();
        this.active.set(false);
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
        const to = movable.indexOf(message);
        if (extend && from !== -1) {
            for (const m of movable.slice(Math.min(from, to), Math.max(from, to) + 1)) {
                this.ids().add(m.id);
            }
        } else if (this.has(message)) {
            this.ids().delete(message.id);
        } else {
            this.ids().add(message.id);
        }
        this.anchor = message.id;
    }
}

Object.assign(Chatter.components, { DropdownItem });

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.action = useService('action');
        this.orm = useService('orm');
        this.moveConfigurations = signal([]);
        useHotkey('escape', () => this.messageMove.stop(), {
            isAvailable: () => this.messageMove.active(),
        });
    },
    get subEnv() {
        const res = super.subEnv;
        this.messageMove ??= new MessageMoveSelection({
            onStart: () => {
                this.state.composerType = false;
                this.closeSearch();
                this.orm
                    .call('mail.message', 'get_route_configurations', [])
                    .then((configurations) =>
                        this.moveConfigurations.set(configurations),
                    );
            },
        });
        Object.assign(res.inChatter, { messageMove: this.messageMove });
        return res;
    },
    get moveCountLabel() {
        const count = this.messageMove.ids().size;
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
    get attClass() {
        const messageMove = this.env.inChatter?.messageMove;
        if (!messageMove?.active()) {
            return super.attClass;
        }
        const movable = isMovable(this.message);
        return {
            ...super.attClass,
            mk_move_selectable: movable,
            mk_move_selected: movable && messageMove.has(this.message),
            mk_move_disabled: !movable,
        };
    },
    onClick(ev) {
        const messageMove = this.env.inChatter?.messageMove;
        if (!messageMove?.active()) {
            return super.onClick(ev);
        }
        if (isMovable(this.message)) {
            messageMove.toggle(this.message, this.props.thread, ev.shiftKey);
        }
    },
});

registerMessageAction('muk-move', {
    condition: ({ message, owner, store, thread }) =>
        Boolean(owner.env.inChatter?.messageMove) &&
        thread?.model !== 'discuss.channel' &&
        store.self_user?.share === false &&
        isMovable(message),
    icon: 'swap_horiz',
    name: _t('Move'),
    onSelected: ({ message, owner }) => owner.env.inChatter.messageMove.start(message),
    sequence: 36,
});
