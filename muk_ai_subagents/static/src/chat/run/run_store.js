import { useEffect } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import {
    sessionEventHandlers,
    sessionSendRoutes,
} from '@muk_ai/chat/session/use_ai_session';

export const DELEGATE_TOOL = 'delegate';

const FINISHED_STATES = ['done', 'error', 'stopped'];
const DELEGATION_KINDS = ['delegation_start', 'delegation_result'];

/**
 * Map a child's colour name onto the class carrying its colour token.
 * @param {string} color one of the eight agent colour names
 * @returns {string} the `mk_agent_<color>` class, blue when there is none
 */
export function colorClass(color) {
    return `mk_agent_${color || 'blue'}`;
}

/**
 * Tell whether a stop reason describes a child that finished on its own terms.
 * @param {string} reason the child's stop_reason
 * @returns {boolean} false for a stop, an error, a budget or an iteration cap
 */
export function isCleanStop(reason) {
    return !reason || reason === 'done';
}

/**
 * Read what a child is blocked on as a pending-ask shaped object.
 * @param {object} child a roster child
 * @returns {object|null} `{kind, text, options, preview, call_id}`, null when free
 */
export function childAsk(child) {
    return (child && child.waiting) || null;
}

export function isFinished(child) {
    return FINISHED_STATES.includes(child.state);
}

/**
 * Tell whether a finished child ended badly.
 * @param {object} child a roster child
 * @returns {boolean} true on an error state or an unclean stop reason
 */
export function isFailed(child) {
    return (
        isFinished(child) &&
        (child.state === 'error' || !isCleanStop(child.stop_reason))
    );
}

/**
 * Format a duration in seconds for a roster row or a result card.
 * @param {*} seconds duration in seconds
 * @returns {string} `12s`, `4m 05s` or `1h 03m`; empty for nothing
 */
export function formatElapsed(seconds) {
    const total = Math.floor(Number(seconds) || 0);
    if (total <= 0) {
        return '';
    }
    const pad = (value) => String(value).padStart(2, '0');
    if (total < 60) {
        return _t('%ss', total);
    }
    if (total < 3600) {
        return _t('%sm %ss', Math.floor(total / 60), pad(total % 60));
    }
    return _t(
        '%sh %sm',
        Math.floor(total / 3600),
        pad(Math.floor((total % 3600) / 60)),
    );
}

/**
 * A child's elapsed time, advanced past the last roster snapshot while it runs.
 * @param {object} child a roster child
 * @param {object|null} run the roster the child came from
 * @returns {number} seconds
 */
export function liveElapsed(child, run) {
    const base = Number(child.elapsed) || 0;
    if (isFinished(child) || !run || !run.receivedAt) {
        return base;
    }
    return base + (Date.now() - run.receivedAt) / 1000;
}

/**
 * How long a child has been blocked on the user, in seconds.
 *
 * The roster stamps when the subagent parked, so the count is right even for
 * someone who opened the conversation long after it happened.
 * @param {object} child a roster child
 * @returns {number} seconds, 0 when the child is not blocked
 */
export function waitingSeconds(child) {
    if (!childAsk(child) || !child.waiting_since) {
        return 0;
    }
    const since = Date.parse(`${child.waiting_since}Z`.replace(' ', 'T'));
    return Number.isFinite(since) ? Math.max(0, (Date.now() - since) / 1000) : 0;
}

/**
 * Say where what is typed will land: a subagent, or the queue of a parked parent.
 *
 * The composer belongs to whatever conversation is on screen, so it says so
 * rather than leaving the user to infer it.
 * @param {object} session the parent session api
 * @returns {string} the placeholder, empty when the core's own applies
 */
export function subagentPlaceholder(session) {
    const open = session.state.subagentOpen;
    if (!open) {
        const ask = session.state.pendingAsk;
        return ask && ask.kind === 'children'
            ? _t('Subagents are working — your message will queue…')
            : '';
    }
    const name = open.agent_name || open.name;
    const child = rosterChild(session, open.id);
    if (child && !isFinished(child)) {
        return _t('Direct %s — reaches it after its current step…', name);
    }
    // A subagent that has reported cannot be re-asked while its siblings are
    // still working: the parent is waiting on a report it already has, and a
    // new turn would never reach it. Say so rather than offer it.
    if (rosterChildren(session).some((entry) => !isFinished(entry))) {
        return _t('%s has reported — ask it more once the run has ended…', name);
    }
    return _t('Ask %s for more…', name);
}

/**
 * Name a subagent in one short line, for a slot that reads as a sentence.
 *
 * A subagent's session name carries its objective so the roster and the
 * breadcrumb can identify it, which is far too long where the name is
 * followed by more words. The agent's name is what the user recognises.
 * @param {object} child a roster child
 * @returns {string} the agent's name, the session name when it has none
 */
export function shortName(child) {
    return (child && (child.agent_name || child.name)) || '';
}

/**
 * Read the subagents of the run the parent session is showing.
 * @param {object} session the parent session api
 * @returns {Array} the roster children, empty when no run is live
 */
export function rosterChildren(session) {
    const run = session.state.subagentRun;
    return (run && run.children) || [];
}

/**
 * Read one subagent of the run by id.
 * @param {object} session the parent session api
 * @param {number} childId the subagent's session id
 * @returns {object|null} the roster child, null when the run has no such subagent
 */
export function rosterChild(session, childId) {
    return rosterChildren(session).find((child) => child.id === childId) || null;
}

/**
 * Read the subagents of the run that are waiting on the user.
 * @param {object} session the parent session api
 * @returns {Array} the blocked roster children, in roster order
 */
export function blockedChildren(session) {
    return rosterChildren(session).filter((child) => childAsk(child));
}

/**
 * Show a child's transcript beside the parent chat.
 * @param {object} session the parent session api
 * @param {object} child `{id, name, agent_name, color}`
 */
export function openChild(session, child) {
    // The roster got you here; in a 600px window it would then sit on top of
    // the transcript you asked for, so it folds away.
    session.state.subagentStripOpen = false;
    session.state.subagentOpen = {
        id: child.id,
        name: child.name || '',
        agent_name: child.agent_name || '',
        color: child.color || '',
    };
}

export function closeChild(session) {
    session.state.subagentOpen = null;
}

/**
 * Drop the roster open under the run strip.
 *
 * The strip keeps its open state on the session rather than in the component,
 * so a card in the transcript can reach for it and it survives a re-render.
 * @param {object} session the parent session api
 */
export function openStrip(session) {
    session.state.subagentStripOpen = true;
}

function stampRun(run) {
    return { ...run, children: run.children || [], receivedAt: Date.now() };
}

function hasDelegation(events) {
    return (events || []).some(
        (event) => event && DELEGATION_KINDS.includes(event.kind),
    );
}

sessionEventHandlers.add('subagent_update', (payload, { state }) => {
    state.subagentRun = stampRun(payload);
});

// Send what was typed to the conversation on screen: opening a subagent
// replaces the transcript, so the composer under it belongs to that subagent.
// One blocked on a question needs an answer, not a steer, which would queue
// text for a turn that cannot start until the question is answered.
sessionSendRoutes.add('muk_ai_subagents.steer', async ({ state, orm }, text) => {
    const target = state.subagentOpen;
    if (!target) {
        return false;
    }
    const message = (text || '').trim();
    if (!message) {
        return true;
    }
    const child = rosterChild({ state }, target.id);
    const ask = childAsk(child);
    if (ask && ask.kind !== 'approval') {
        await orm.call('muk_ai.session', 'answer', [target.id, message]);
        return true;
    }
    const run = await orm.call('muk_ai.session', 'subagent_steer', [
        state.sessionId,
        target.id,
        message,
    ]);
    if (run) {
        state.subagentRun = stampRun(run);
    }
    return true;
});

/**
 * Keep the parent session's delegation roster loaded for the conversation.
 *
 * The roster arrives live over the bus; on load it is fetched once when the
 * transcript shows a delegation, so a chat that never delegated costs nothing.
 * @param {object} session the parent session api
 */
export function useSubagentRun(session) {
    const orm = useService('orm');
    useEffect(
        () => {
            session.state.subagentRun = null;
            session.state.subagentOpen = null;
            session.state.subagentStripOpen = false;
        },
        () => [session.state.sessionId],
    );
    useEffect(
        (sessionId, loading) => {
            if (!sessionId || loading || !hasDelegation(session.state.events)) {
                return;
            }
            orm.call('muk_ai.session', 'subagent_run_snapshot', [sessionId]).then(
                (run) => {
                    if (run && session.state.sessionId === sessionId) {
                        session.state.subagentRun = stampRun(run);
                    }
                },
            );
        },
        () => [session.state.sessionId, session.state.loading],
    );
}
