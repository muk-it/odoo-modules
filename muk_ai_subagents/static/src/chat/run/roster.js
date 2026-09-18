import { childAsk, isFailed, isFinished } from '@muk_ai_subagents/chat/run/run_store';

/**
 * Split a roster into the groups the run strip draws, by urgency.
 *
 * Ordering is what the user has to act on first, never what happened first:
 * a subagent waiting on them, then one that stopped early, then the ones still
 * working, then the ones that finished. Finished rows stay listed while
 * anything still runs; once the whole run is idle they fold into a counted
 * `Done (n)` group, except the row currently open, which stays in view.
 * @param {Array} children the roster children
 * @param {object} [options] `openId` names the child whose transcript is open
 * @returns {{needsYou: Array, failed: Array, working: Array, done: Array, collapsed: Array}}
 */
export function groupRoster(children, { openId = null } = {}) {
    const needsYou = [];
    const failed = [];
    const working = [];
    const finished = [];
    for (const child of children || []) {
        if (!child) {
            continue;
        }
        if (childAsk(child)) {
            needsYou.push(child);
        } else if (isFailed(child)) {
            failed.push(child);
        } else if (isFinished(child)) {
            finished.push(child);
        } else {
            working.push(child);
        }
    }
    const idle = !needsYou.length && !working.length;
    const pinned = (child) => child.id === openId;
    return {
        needsYou,
        failed,
        working,
        done: idle ? finished.filter(pinned) : finished,
        collapsed: idle ? finished.filter((child) => !pinned(child)) : [],
    };
}
