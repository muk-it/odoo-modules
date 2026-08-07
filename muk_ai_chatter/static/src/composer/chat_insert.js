import { patch } from '@web/core/utils/patch';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';

// Where an answer goes when a session was handed over from a composer, kept
// per session because the chat window outlives the panel that opened it.
const inserters = new Map();

/**
 * Say where the answers of a handed-over session should be put.
 * @param {number} sessionId the session the chat window shows
 * @param {(text: string) => void} insert puts an answer in the composer
 */
export function rememberInsert(sessionId, insert) {
    inserters.set(sessionId, insert);
}

patch(ChatWindow.prototype, {
    /**
     * Offer the way back to the composer this session came from.
     *
     * Read for each render rather than kept: the composer hands its session
     * over after the window it may already be shown in was set up.
     *
     * @override
     */
    setup() {
        super.setup();
        Object.defineProperty(this.session, 'insertText', {
            configurable: true,
            get: () => {
                const insert = inserters.get(this.props.sessionId);
                return insert ? (text) => text && insert(String(text)) : null;
            },
        });
    },
});
