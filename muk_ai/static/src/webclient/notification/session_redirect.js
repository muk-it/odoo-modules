// @odoo-module

import { patch } from '@web/core/utils/patch';

import { Messaging } from '@mail/core/common/messaging_service';
import { MessagingMenu } from '@mail/core/web/messaging_menu';

export const AI_SESSION_MODEL = 'muk_ai.session';

/**
 * Return the client action descriptor that opens the AI chat for a session.
 *
 * @param {number} sessionId Database id of the ``muk_ai.session`` record.
 * @returns {object} An ``ir.actions.client`` descriptor for ``muk_ai.chat``.
 */
export function aiSessionChatAction(sessionId) {
    return {
        type: 'ir.actions.client',
        tag: 'muk_ai.chat',
        params: { session_id: sessionId },
    };
}

patch(Messaging.prototype, {
    openDocument({ id, model }) {
        if (model === AI_SESSION_MODEL) {
            this.env.services.action.doAction(aiSessionChatAction(id));
            return;
        }
        return super.openDocument(...arguments);
    },
});

patch(MessagingMenu.prototype, {
    onClickThread(isMarkAsRead, thread) {
        if (!isMarkAsRead && thread && thread.model === AI_SESSION_MODEL) {
            this.env.services.action.doAction(aiSessionChatAction(thread.id));
            return;
        }
        return super.onClickThread(...arguments);
    },
});
