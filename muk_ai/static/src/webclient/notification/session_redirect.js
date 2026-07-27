// @odoo-module

import { registerPatch } from '@mail/model/model_core';

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

registerPatch({
    name: 'Messaging',
    recordMethods: {
        /**
         * Send AI sessions to the chat client action instead of a form view.
         *
         * Odoo 16 keeps messaging in its legacy model registry and routes
         * notification and preview clicks through this method, so patching it
         * covers what later branches patch separately on Store, Thread and
         * MessagingMenu.
         *
         * @param {{id: number, model: string}} payload target record
         */
        async openDocument({ id, model }) {
            if (model === AI_SESSION_MODEL) {
                this.env.services.action.doAction(aiSessionChatAction(id));
                return;
            }
            return this._super({ id, model });
        },
    },
});
