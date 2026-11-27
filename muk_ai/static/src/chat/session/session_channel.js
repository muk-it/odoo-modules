import { useEffect } from '@odoo/owl';

import { useService } from '@web/core/utils/hooks';

import { makeRefCount } from '@muk_ai/chat/session/refcount';

const followers = makeRefCount();

const RUN_CHECK_MS = 10000;

const RUNNING = ['running', 'compacting'];

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

/**
 * Catch the end of a run the bus did not announce.
 *
 * While the component waits on a run, the session's state is read every few
 * seconds; `onEnd` runs once the run is over.
 * @param {function(): (number|null)} getSessionId reads the displayed session
 * @param {function(): boolean} isRunning whether the component waits on a run
 * @param {function(): void} onEnd catches the component up with the session
 */
export function useRunWatch(getSessionId, isRunning, onEnd) {
    const orm = useService('orm');
    useEffect(
        (sessionId, running) => {
            if (!sessionId || !running) {
                return;
            }
            const timer = setInterval(async () => {
                const [values] = await orm.silent
                    .read('muk_ai.session', [sessionId], ['state'])
                    .catch(() => [{ state: RUNNING[0] }]);
                if (isRunning() && !RUNNING.includes(values?.state)) {
                    onEnd();
                }
            }, RUN_CHECK_MS);
            return () => clearInterval(timer);
        },
        () => [getSessionId(), isRunning()],
    );
}
