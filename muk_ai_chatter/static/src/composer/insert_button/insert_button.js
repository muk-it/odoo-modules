/** @odoo-module */

import { patch } from '@web/core/utils/patch';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';

const inserters = new Map();

/**
 * Say where the answers of a session handed over from a composer go.
 * @param {number} sessionId the session the chat window shows
 * @param {(text: string) => void} insert puts an answer in the composer
 */
export function rememberInsert(sessionId, insert) {
    inserters.set(sessionId, insert);
}

/**
 * Return where the answers of a session go, nowhere for an ordinary chat.
 * @param {number} sessionId the session the chat window shows
 * @returns {((text: string) => void)|undefined} puts an answer in the composer
 */
export function insertFor(sessionId) {
    return inserters.get(sessionId);
}

patch(ChatWindow.prototype, {
    setup() {
        super.setup();
        Object.defineProperty(this.session, 'insertText', {
            configurable: true,
            get: () => insertFor(this.props.sessionId),
        });
    },
});
