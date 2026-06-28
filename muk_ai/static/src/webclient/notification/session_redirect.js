import { patch } from '@web/core/utils/patch';

import { Store } from '@mail/core/common/store_service';
import { Thread } from '@mail/core/common/thread_model';
import { MessagingMenu } from '@mail/core/public_web/messaging_menu';

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

patch(Store.prototype, {
    openDocument({ id, model }) {
        if (model === AI_SESSION_MODEL) {
            this.env.services.action.doAction(aiSessionChatAction(id));
            return;
        }
        return super.openDocument(...arguments);
    },
});

patch(Thread.prototype, {
    get openRecordActionRequest() {
        if (this.model === AI_SESSION_MODEL) {
            return aiSessionChatAction(this.id);
        }
        return super.openRecordActionRequest;
    },
});

patch(MessagingMenu.prototype, {
    onClickInboxMsg(isMarkAsRead, msg) {
        const thread = msg.thread;
        if (!isMarkAsRead && thread && thread.model === AI_SESSION_MODEL) {
            this.env.services.action.doAction(aiSessionChatAction(thread.id));
            msg.setDone();
            return;
        }
        return super.onClickInboxMsg(...arguments);
    },
});
