import { useEffect } from '@odoo/owl';

import { useService } from '@web/core/utils/hooks';

import { makeRefCount } from '@muk_ai/chat/session/refcount';

const followers = makeRefCount();

/**
 * Name the bus channel a session publishes its transcript on.
 * @param {number} sessionId the session to listen to
 * @returns {string} the channel name the websocket resolves to the record
 */
export function sessionChannel(sessionId) {
    return `muk_ai.session_${sessionId}`;
}

/**
 * Follow a session's transcript for as long as the component shows it.
 *
 * The server grants the channel only to somebody who may read the chat, so a
 * component asks for whichever session it displays and lets the subscription
 * lapse once nothing shows it any more.
 * @param {function(): (number|null)} getSessionId reads the displayed session
 */
export function useSessionChannel(getSessionId) {
    const bus = useService('bus_service');
    let held = null;
    const drop = () => {
        if (held && followers.release(held)) {
            bus.deleteChannel(sessionChannel(held));
        }
        held = null;
    };
    useEffect(
        (sessionId) => {
            if (!sessionId) {
                return;
            }
            held = sessionId;
            if (followers.acquire(sessionId)) {
                bus.addChannel(sessionChannel(sessionId));
            }
            return drop;
        },
        () => [getSessionId()],
    );
}
