import { useEffect } from '@odoo/owl';

import { makeRefCount } from '@muk_ai/chat/session/refcount';

const openSessions = makeRefCount();

/**
 * Tell whether this tab may answer a session's client actions.
 *
 * A client tool runs against the view the user is talking about, so only a
 * tab with that chat on screen may answer for it — and never a reader, whose
 * browser is not the one the owner is talking about.
 * @param {number} sessionId the session a client action is waiting on
 * @returns {boolean} true while a chat surface here steers it
 */
export function isChatOpen(sessionId) {
    return openSessions.has(sessionId);
}

/**
 * Record that a chat surface started showing a session.
 * @param {number} sessionId the session now on screen
 */
export function registerOpenSession(sessionId) {
    openSessions.acquire(sessionId);
}

/**
 * Record that a chat surface stopped showing a session.
 * @param {number} sessionId the session no longer on screen
 */
export function unregisterOpenSession(sessionId) {
    openSessions.release(sessionId);
}

/**
 * Register the session a chat surface shows for as long as it shows it.
 * @param {function(): (number|null)} getSessionId reads the displayed session
 */
export function useOpenSession(getSessionId) {
    let held = null;
    const drop = () => {
        if (held) {
            unregisterOpenSession(held);
            held = null;
        }
    };
    useEffect(
        (sessionId) => {
            if (!sessionId) {
                return;
            }
            held = sessionId;
            registerOpenSession(sessionId);
            return drop;
        },
        () => [getSessionId()],
    );
}
