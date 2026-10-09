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

patch(ChatWindow.prototype, {
    setup() {
        super.setup();
        Object.defineProperty(this.session, 'insertText', {
            configurable: true,
            get: () => inserters.get(this.props.sessionId),
        });
    },
});
