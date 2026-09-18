import { Component, onMounted, onWillUnmount, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { useSessionState } from '@muk_ai/chat/session/use_ai_session';
import { formatCost } from '@muk_ai/chat/utils';

import { groupRoster } from '@muk_ai_subagents/chat/run/roster';
import {
    childAsk,
    colorClass,
    formatElapsed,
    isFailed,
    isFinished,
    liveElapsed,
    openChild,
    rosterChildren,
    shortName,
    waitingSeconds,
} from '@muk_ai_subagents/chat/run/run_store';

const TICK_MS = 1000;
const MAX_DOTS = 5;

/**
 * What the subagents are doing, in one line that never leaves the screen.
 *
 * The line sits above the composer, where the user is already looking, and
 * says only what it takes to decide whether to intervene. Opening it drops
 * the roster down; opening a row drops that subagent's detail under it. The
 * conversation beside it never moves, and nothing floats over the card the
 * user may have to answer.
 */
export class SubagentRunStrip extends Component {
    static template = 'muk_ai_subagents.SubagentRunStrip';
    static props = {
        session: { type: Object },
    };
    setup() {
        this.orm = useService('orm');
        this.session = useSessionState(this.props.session);
        this.state = useState({
            detailId: null,
            peek: null,
            peekLoading: false,
            doneExpanded: false,
            tick: 0,
        });
        onMounted(() => {
            this.tickInterval = window.setInterval(() => {
                this.state.tick += 1;
            }, TICK_MS);
        });
        onWillUnmount(() => window.clearInterval(this.tickInterval));
    }

    // ----------------------------------------------------------
    // The run
    // ----------------------------------------------------------

    get expanded() {
        return !!this.session.state.subagentStripOpen;
    }
    get run() {
        return this.session.state.subagentRun;
    }
    get children() {
        return rosterChildren(this.session);
    }
    get hasRun() {
        return this.children.length > 0;
    }
    get groups() {
        return groupRoster(this.children, { openId: this.openId });
    }
    get openId() {
        const open = this.session.state.subagentOpen;
        return open ? open.id : null;
    }
    get blocked() {
        return this.groups.needsYou;
    }
    get anyActive() {
        const groups = this.groups;
        return groups.needsYou.length + groups.working.length > 0;
    }

    // ----------------------------------------------------------
    // The collapsed line
    // ----------------------------------------------------------

    get dots() {
        return this.children.slice(0, MAX_DOTS);
    }
    get moreDots() {
        const rest = this.children.length - MAX_DOTS;
        return rest > 0 ? _t('+%s', rest) : '';
    }
    get summary() {
        void this.state.tick;
        const blocked = this.blocked;
        if (blocked.length) {
            const elapsed = formatElapsed(waitingSeconds(blocked[0]));
            const name = shortName(blocked[0]);
            const first = elapsed
                ? _t('%(name)s has been waiting %(elapsed)s', { name, elapsed })
                : _t('%s is waiting for you', name);
            return blocked.length > 1
                ? _t('%(first)s · %(count)s more waiting', {
                      first,
                      count: blocked.length - 1,
                  })
                : first;
        }
        const working = this.groups.working;
        const stuck = working.filter((child) => child.stuck).length;
        if (stuck) {
            return stuck === 1
                ? _t('1 subagent is repeating itself')
                : _t('%s subagents are repeating themselves', stuck);
        }
        if (working.length) {
            return working.length === 1
                ? _t('1 subagent working')
                : _t('%s subagents working', working.length);
        }
        const failed = this.groups.failed.length;
        if (failed) {
            return failed === 1
                ? _t('1 subagent stopped early')
                : _t('%s subagents stopped early', failed);
        }
        const count = this.children.length;
        return count === 1 ? _t('1 subagent done') : _t('%s subagents done', count);
    }
    get summaryClass() {
        const blocked = this.blocked;
        if (blocked.length) {
            return `mk_run_strip_blocked ${colorClass(blocked[0].color)}`;
        }
        if (this.groups.working.some((child) => child.stuck)) {
            return 'mk_run_strip_stuck';
        }
        return this.groups.failed.length ? 'mk_run_strip_failed' : '';
    }
    /**
     * Sum the run up in one sentence, for the single live region.
     *
     * Mirroring every subagent's activity into a live region would announce N
     * streams at once; one sentence that only changes when the counts change
     * says the same thing without the noise.
     * @returns {string} e.g. `2 subagents working, 1 needs you`
     */
    get liveSummary() {
        const groups = this.groups;
        const parts = [];
        if (groups.working.length) {
            parts.push(_t('%s working', groups.working.length));
        }
        if (groups.needsYou.length) {
            parts.push(_t('%s needing you', groups.needsYou.length));
        }
        if (groups.failed.length) {
            parts.push(_t('%s stopped early', groups.failed.length));
        }
        const done = groups.done.length + groups.collapsed.length;
        if (done) {
            parts.push(_t('%s done', done));
        }
        return _t('Subagents: %s', parts.join(', '));
    }
    get toggleLabel() {
        return this.expanded ? _t('Hide the subagents') : _t('Show the subagents');
    }

    // ----------------------------------------------------------
    // The roster
    // ----------------------------------------------------------

    get sections() {
        const groups = this.groups;
        return [
            { key: 'needs_you', label: _t('Needs you'), children: groups.needsYou },
            { key: 'failed', label: _t('Stopped early'), children: groups.failed },
            { key: 'working', label: _t('Working'), children: groups.working },
            { key: 'done', label: _t('Done'), children: groups.done },
        ].filter((section) => section.children.length);
    }
    get collapsed() {
        return this.groups.collapsed;
    }
    get doneLabel() {
        return _t('Done (%s)', this.collapsed.length);
    }
    get totalCost() {
        return formatCost(this.run ? this.run.total_cost : 0);
    }
    get costLimit() {
        const limit = this.run && this.run.cost_limit;
        return limit ? formatCost(limit) : '';
    }
    get overBudget() {
        const run = this.run;
        return !!(run && run.cost_limit && run.total_cost >= run.cost_limit);
    }
    /**
     * Tell whether the run has spent enough of its ceiling to be worth saying.
     *
     * A meter that never leaves the corner of the eye makes people spend less
     * and explore less, so the resting line stays quiet until the budget is
     * nearly gone. The full figure is always one click away in the footer.
     * @returns {boolean} true past four fifths of the limit
     */
    get costWorthShowing() {
        const run = this.run;
        return !!(run && run.cost_limit && run.total_cost >= run.cost_limit * 0.8);
    }
    get canWrite() {
        return this.session.canWrite();
    }
    colorClass(color) {
        return colorClass(color);
    }
    rowClass(child) {
        return {
            [colorClass(child.color)]: true,
            mk_agent_row_blocked: !!childAsk(child),
            mk_agent_row_failed: isFailed(child),
            mk_agent_row_stuck: !!child.stuck && !isFinished(child),
            mk_agent_row_done: isFinished(child) && !isFailed(child),
            mk_agent_row_open: child.id === this.openId,
            mk_agent_row_detail: child.id === this.state.detailId,
        };
    }
    activity(child) {
        const ask = childAsk(child);
        if (ask) {
            return (
                ask.text ||
                (ask.kind === 'approval'
                    ? _t('Waiting for your approval')
                    : _t('Waiting for your answer'))
            );
        }
        return child.activity || child.summary || '';
    }
    elapsed(child) {
        void this.state.tick;
        return formatElapsed(liveElapsed(child, this.run));
    }
    isBlocked(child) {
        return !!childAsk(child);
    }
    isStuck(child) {
        return !!child.stuck && !isFinished(child) && !childAsk(child);
    }
    isFailed(child) {
        return isFailed(child);
    }
    isFinished(child) {
        return isFinished(child);
    }

    // ----------------------------------------------------------
    // One subagent's detail
    // ----------------------------------------------------------

    get detailChild() {
        return this.children.find((child) => child.id === this.state.detailId) || null;
    }
    get recentCalls() {
        return this.state.peek || [];
    }
    get detailCost() {
        const child = this.detailChild;
        return formatCost(child ? child.cost : 0);
    }
    canStop(child) {
        return !isFinished(child) && this.canWrite;
    }

    // ----------------------------------------------------------
    // Handlers
    // ----------------------------------------------------------

    toggle() {
        this.session.state.subagentStripOpen = !this.expanded;
        if (!this.expanded) {
            this.state.detailId = null;
        }
    }
    toggleDone() {
        this.state.doneExpanded = !this.state.doneExpanded;
    }
    async onRowClick(child) {
        if (this.state.detailId === child.id) {
            this.state.detailId = null;
            return;
        }
        this.state.detailId = child.id;
        this.state.peek = null;
        this.state.peekLoading = true;
        try {
            this.state.peek = await this.orm.call('muk_ai.session', 'subagent_peek', [
                this.session.state.sessionId,
                child.id,
            ]);
        } finally {
            this.state.peekLoading = false;
        }
    }
    onRowKeydown(child, ev) {
        if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            this.onRowClick(child);
        } else if (ev.key === 'Escape' && this.state.detailId === child.id) {
            ev.preventDefault();
            this.state.detailId = null;
        }
    }
    onOpen(child) {
        openChild(this.session, child);
    }
    onStop(child) {
        return this.orm.call('muk_ai.session', 'subagent_stop', [
            this.session.state.sessionId,
            child.id,
        ]);
    }
    onStopAll() {
        return this.orm.call('muk_ai.session', 'subagent_stop_all', [
            this.session.state.sessionId,
        ]);
    }
}
