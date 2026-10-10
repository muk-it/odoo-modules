import { Component, markup, useEffect, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { renderMarkdown } from '@muk_ai/core/markdown/markdown';
import { turnBuilders, turnRenderers } from '@muk_ai/chat/session/turns';
import { useSessionState } from '@muk_ai/chat/session/use_ai_session';
import { formatCost, formatError } from '@muk_ai/chat/utils';

import {
    activityText,
    askText,
    byUrgency,
    childStatus,
    endText,
    formatElapsed,
    liveElapsed,
    openChat,
    reportLine,
} from '@muk_ai_subagents/chat/run/run';

const TICK_MS = 1000;
const STATUS_ICONS = {
    needs_you: 'fa-hand-paper-o',
    working: 'fa-circle-o-notch',
    failed: 'fa-exclamation-triangle',
    stopped: 'fa-stop-circle-o',
    done: 'fa-check-circle',
};

/**
 * What a waiting subagent asks, answered in place: its approval with the
 * preview of the call, or its question with a field for the answer, acting
 * on the subagent's own chat.
 */
export class SubagentAsk extends Component {
    static template = 'muk_ai_subagents.SubagentAsk';
    static props = {
        child: { type: Object },
        readonly: { type: Boolean },
    };
    setup() {
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.state = useState({ answer: '', busy: false });
    }
    get ask() {
        return this.props.child.ask || {};
    }
    async call(method, args = []) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call('muk_ai.session', method, [
                this.props.child.id,
                ...args,
            ]);
        } catch (error) {
            this.notification.add(formatError(error), { type: 'danger' });
        } finally {
            this.state.busy = false;
        }
    }
    send(text) {
        const answer = (text || '').trim();
        if (answer) {
            this.state.answer = '';
            return this.call('answer', [answer]);
        }
    }
    onKeydown(ev) {
        if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.send(this.state.answer);
        }
    }
}

/**
 * One subagent of a run: who it is, what it does or needs, and once it ended
 * its report, with the way into its own chat.
 */
export class SubagentRow extends Component {
    static template = 'muk_ai_subagents.SubagentRow';
    static components = { SubagentAsk };
    static props = {
        child: { type: Object },
        run: { type: Object },
        session: { type: Object },
        now: { type: Number },
    };
    setup() {
        this.services = {
            action: useService('action'),
            ui: useService('ui'),
            chatWindow: useService('muk_ai.chat_window'),
        };
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.state = useState({ open: null });
        this.renderMarkdown = (text) => markup(renderMarkdown(text));
    }
    get status() {
        return childStatus(this.props.child);
    }
    get open() {
        return this.state.open ?? ['needs_you', 'failed'].includes(this.status);
    }
    get icon() {
        return this.props.child.repeating ? 'fa-repeat' : STATUS_ICONS[this.status];
    }
    get initial() {
        return (this.props.child.agent_name || this.props.child.name || '?')
            .charAt(0)
            .toUpperCase();
    }
    get elapsed() {
        return formatElapsed(
            liveElapsed(this.props.child, this.props.run, this.props.now),
        );
    }
    get line() {
        const child = this.props.child;
        if (this.status === 'needs_you') {
            return askText(child);
        }
        if (this.status === 'working') {
            return activityText(child);
        }
        return endText(child) || reportLine(child.report);
    }
    get readonly() {
        return !this.props.session.canWrite();
    }
    get canStop() {
        return ['working', 'needs_you'].includes(this.status) && !this.readonly;
    }
    toggle() {
        this.state.open = !this.open;
    }
    onOpen() {
        openChat(this.services, this.props.child.id);
    }
    async stop() {
        try {
            await this.orm.call('muk_ai.session', 'action_stop', [this.props.child.id]);
        } catch (error) {
            this.notification.add(formatError(error), { type: 'danger' });
        }
    }
}

/**
 * Subagents and what they did. Docked above the composer it is the run while
 * subagents work, who needs the user first and the finished ones on request;
 * in the transcript it is one delegate call, its reports once they ended.
 */
export class SubagentRunCard extends Component {
    static template = 'muk_ai_subagents.SubagentRunCard';
    static components = { SubagentRow };
    static props = {
        turn: { type: Object },
        session: { type: Object },
        docked: { type: Boolean, optional: true },
    };
    static defaultProps = { docked: false };
    setup() {
        this.session = useSessionState(this.props.session);
        this.notification = useService('notification');
        this.state = useState({ now: Date.now(), showFinished: false });
        useEffect(
            (ticking) => {
                if (ticking) {
                    const interval = setInterval(() => {
                        this.state.now = Date.now();
                    }, TICK_MS);
                    return () => clearInterval(interval);
                }
            },
            () => [this.live && this.props.docked],
        );
    }
    get run() {
        return this.session.state.subagents || { children: [] };
    }
    get children() {
        const roster = new Map(this.run.children.map((child) => [child.id, child]));
        return byUrgency(
            this.props.turn.children.map(
                (child) =>
                    roster.get(child.id) || { ...child, state: 'new', elapsed: 0 },
            ),
        );
    }
    /**
     * The subagents the card lists: in the transcript once they ended, docked
     * the working ones and the finished ones on request.
     * @returns {Array} roster entries
     */
    get rows() {
        if (!this.props.docked) {
            return this.live ? [] : this.children;
        }
        if (this.state.showFinished) {
            return this.children;
        }
        return this.children.filter((child) =>
            ['working', 'needs_you'].includes(childStatus(child)),
        );
    }
    get finishedToggle() {
        const count = this.children.length - this.rows.length;
        if (this.state.showFinished) {
            return _t('Hide finished');
        }
        return count ? _t('Show %s finished', count) : '';
    }
    get counts() {
        const counts = {};
        for (const child of this.children) {
            const status = childStatus(child);
            counts[status] = (counts[status] || 0) + 1;
        }
        return counts;
    }
    get live() {
        return !!(this.counts.working || this.counts.needs_you);
    }
    get title() {
        const { working = 0, needs_you: waiting = 0 } = this.counts;
        const total = this.children.length;
        if (!this.live) {
            const longest = Math.max(...this.children.map((child) => child.elapsed));
            const reported =
                total === 1
                    ? _t('1 subagent reported')
                    : _t('%s subagents reported', total);
            return longest > 0
                ? _t('%(reported)s in %(time)s', {
                      reported,
                      time: formatElapsed(longest),
                  })
                : reported;
        }
        const parts = [];
        if (waiting) {
            parts.push(waiting === 1 ? _t('1 needs you') : _t('%s need you', waiting));
        }
        if (working) {
            parts.push(_t('%s of %s working', working, total));
        }
        return parts.join(' · ');
    }
    get cost() {
        return formatCost(
            this.children.reduce((sum, child) => sum + (child.cost || 0), 0),
        );
    }
    get canStopAll() {
        return this.live && this.props.docked && this.session.canWrite();
    }
    async stopAll() {
        try {
            const snapshot = await this.session.callSession('action_stop_subagents');
            this.session.applySnapshot(snapshot);
        } catch (error) {
            this.notification.add(
                _t('Failed to stop the subagents: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
}

turnBuilders.add('delegation_start', (entry) =>
    entry.children?.length
        ? { role: 'subagent_run', callId: entry.call_id, children: entry.children }
        : null,
);
turnRenderers.add('subagent_run', SubagentRunCard);
