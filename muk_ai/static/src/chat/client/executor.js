import { isChatOpen } from '@muk_ai/chat/session/open_sessions';

/**
 * Parse a client-action arguments payload into a plain object.
 * The bus carries arguments either as a JSON string or an object.
 * @param {*} raw the raw arguments value
 * @returns {object|null} the parsed arguments, an empty object when no
 *     arguments were sent, or `null` when the payload is corrupt or
 *     truncated and the action must be rejected instead of executed
 */
export function parseArguments(raw) {
    if (raw && typeof raw === 'object') {
        return raw;
    }
    if (typeof raw === 'string' && raw.trim()) {
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch {
            return null;
        }
    }
    return {};
}

const running = new Map();

/**
 * Run a session's client actions one after the other, in the order the
 * model called them: the tools of one batch work on the same page, and the
 * session lock turns a concurrent post away.
 * @param {number} sessionId the paused session
 * @param {Function} task `async () => void` the action to run
 * @returns {Promise} the action's outcome
 */
function inTurn(sessionId, task) {
    const next = (running.get(sessionId) || Promise.resolve()).then(task);
    running.set(
        sessionId,
        next.catch(() => {}),
    );
    return next;
}

/**
 * Build a `muk_ai.event` bus listener that executes client-tool actions.
 *
 * Shared plumbing for every webclient-side client-tool executor: filters
 * client-action events down to the given tool set, deduplicates call ids
 * (per tab via a local set, across tabs via the Web Locks API when
 * available), scopes execution to the tab holding the session's chat
 * window (that tab owns the page the user is talking about), rejects
 * corrupt argument payloads, and posts the handler outcome back via
 * `submit_client_result` / `reject_client_action`.
 *
 * @param {object} spec the executor specification
 * @param {object} spec.orm the orm service
 * @param {Function} spec.contains `(name) => boolean` tool-name filter
 * @param {Function} spec.execute `async (name, args) => result` tool runner
 * @param {Function} [spec.defer] `() => ms` optional pre-run delay provider
 * @returns {Function} the bus event listener
 */
export function makeClientToolListener({ orm, contains, execute, defer }) {
    const handled = new Set();

    async function run(sessionId, callId, name, rawArgs) {
        const call = (method, args, kwargs) =>
            orm.call('muk_ai.session', method, [sessionId, callId, ...args], kwargs);
        const args = parseArguments(rawArgs);
        if (args === null) {
            await call('reject_client_action', [], {
                reason: 'client received corrupt or truncated tool arguments',
            }).catch(() => {});
            return;
        }
        try {
            await call('submit_client_result', [await execute(name, args)]);
        } catch (error) {
            await call('reject_client_action', [], {
                reason: String(error?.message || error || 'client tool failed'),
            }).catch(() => {});
        }
    }

    function dispatch(sessionId, callId, name, rawArgs) {
        return inTurn(sessionId, () => run(sessionId, callId, name, rawArgs));
    }

    function dispatchOncePerBrowser(sessionId, callId, name, rawArgs) {
        // two tabs can hold the same session's chat window; the Web Locks
        // API elects a single executor across them (first tab wins). The
        // lock is held until the tab closes so a throttled sibling waking
        // up later can never re-execute the same call.
        if (navigator.locks?.request) {
            navigator.locks.request(
                `muk_ai.client_action.${callId}`,
                { ifAvailable: true },
                async (lock) => {
                    if (!lock) {
                        return;
                    }
                    await dispatch(sessionId, callId, name, rawArgs);
                    await new Promise(() => {});
                },
            );
        } else {
            dispatch(sessionId, callId, name, rawArgs);
        }
    }

    return function onEvent(event) {
        if (!event || event.type !== 'log') {
            return;
        }
        const payload = event.payload || {};
        if (payload.kind !== 'client_action' || !payload.call_id) {
            return;
        }
        if (!contains(payload.name) || handled.has(payload.call_id)) {
            return;
        }
        if (!isChatOpen(event.session_id)) {
            return;
        }
        handled.add(payload.call_id);
        const run = () =>
            dispatchOncePerBrowser(
                event.session_id,
                payload.call_id,
                payload.name,
                payload.arguments,
            );
        const delay = defer ? defer() : 0;
        if (delay > 0) {
            setTimeout(run, delay);
        } else {
            run();
        }
    };
}
