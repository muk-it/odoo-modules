import { Component, proxy, signal, t, useEffect, useProps, usePlugin } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { UIPlugin } from '@web/core/ui/ui_plugin';

import { AIChatPlugin, useAISession } from '@muk_ai/core/chat_plugin/chat_plugin';
import { renderMarkdown } from '@muk_ai/core/markdown/markdown';
import { turnBuilders, turnRenderers } from '@muk_ai/core/session/turns';
import { formatCost, formatError } from '@muk_ai/core/utils/utils';
import { ChatTurn } from '@muk_ai/chat/turn/turn';

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
    needs_you: 'front_hand',
    working: 'progress_activity',
    failed: 'warning',
    stopped: 'stop_circle',
    done: 'check_circle',
};

/**
 * What a waiting subagent asks, answered in place: its approval card, or its
 * question with a field for the answer, acting on the subagent's own chat.
 */
export class SubagentAsk extends Component {
    static template = 'muk_ai_subagents.SubagentAsk';
    static components = { ChatTurn };
    props = useProps({ childId: t.number() });
    session = useAISession(() => this.props.childId);
    answer = signal('');
    get turn() {
        const session = this.session();
        const callId = session?.data.pending_ask?.call_id;
        const block = callId
            ? session.turns
                  .flatMap((turn) => turn.blocks || [])
                  .findLast((item) => item.type === 'ask' && item.callId === callId)
            : null;
        return block
            ? { role: 'assistant', blocks: [block], sources: [], attachments: [] }
            : null;
    }
    get question() {
        const session = this.session();
        const ask = session?.data.pending_ask;
        return (
            ask?.kind === 'question' && ask.resolution !== 'yesno' && !session.readonly
        );
    }
    async send() {
        const text = this.answer().trim();
        const session = this.session();
        if (text && session) {
            this.answer.set('');
            session.state.input = text;
            await session.send();
        }
    }
    onKeydown(ev) {
        if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.send();
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
    props = useProps({
        child: t.object(),
        run: t.object(),
        session: t.object(),
        now: t.number(),
    });
    chat = usePlugin(AIChatPlugin);
    ui = usePlugin(UIPlugin);
    state = proxy({ open: null });
    renderMarkdown = renderMarkdown;
    get status() {
        return childStatus(this.props.child);
    }
    get open() {
        return this.state.open ?? ['needs_you', 'failed'].includes(this.status);
    }
    get icon() {
        return STATUS_ICONS[this.status];
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
    get canStop() {
        return (
            ['working', 'needs_you'].includes(this.status) &&
            !this.props.session.readonly
        );
    }
    toggle() {
        this.state.open = !this.open;
    }
    onOpen() {
        openChat(this.chat, this.ui.isSmall(), this.props.child.id);
    }
    async stop() {
        try {
            await this.chat.orm.call('muk_ai.session', 'action_stop', [
                this.props.child.id,
            ]);
        } catch (error) {
            this.chat.notification.add(formatError(error), { type: 'danger' });
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
    props = useProps({
        turn: t.object(),
        session: t.object(),
        docked: t.boolean().optional(false),
    });
    now = signal(Date.now());
    showFinished = signal(false);
    setup() {
        useEffect(() => {
            if (this.live && this.props.docked) {
                const interval = setInterval(() => this.now.set(Date.now()), TICK_MS);
                return () => clearInterval(interval);
            }
        });
    }
    get run() {
        return this.props.session.data.subagents || { children: [] };
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
        if (this.showFinished()) {
            return this.children;
        }
        return this.children.filter((child) =>
            ['working', 'needs_you'].includes(childStatus(child)),
        );
    }
    get finishedToggle() {
        const count = this.children.length - this.rows.length;
        if (this.showFinished()) {
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
        return this.live && this.props.docked && !this.props.session.readonly;
    }
    stopAll() {
        return this.props.session.run(
            'action_stop_subagents',
            [],
            _t('Failed to stop the subagents'),
        );
    }
}

turnBuilders.add('delegation_start', (entry) =>
    entry.children?.length
        ? { role: 'subagent_run', callId: entry.call_id, children: entry.children }
        : null,
);
turnRenderers.add('subagent_run', SubagentRunCard);
