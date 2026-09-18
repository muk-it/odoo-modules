import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import { turnBuilders, turnRenderers } from '@muk_ai/chat/session/turns';
import { formatCost } from '@muk_ai/chat/utils';

import {
    colorClass,
    formatElapsed,
    isCleanStop,
    openChild,
    openStrip,
} from '@muk_ai_subagents/chat/run/run_store';

/**
 * Build the one-line spawn card from a `delegation_start` event.
 * @param {object} entry the session event
 * @returns {object|null} a `subagent_spawn` turn, null without children
 */
function buildSpawnTurn(entry) {
    const children = (entry.children || []).filter((child) => child && child.id);
    if (!children.length) {
        return null;
    }
    return { role: 'subagent_spawn', children };
}

/**
 * Build the per-child result card from a `delegation_result` event.
 * @param {object} entry the session event
 * @returns {object|null} a `subagent_result` turn, null without a child id
 */
function buildResultTurn(entry) {
    if (!entry.child_id) {
        return null;
    }
    return {
        role: 'subagent_result',
        childId: entry.child_id,
        name: entry.name || '',
        agentName: entry.agent_name || '',
        color: entry.color || '',
        summary: entry.summary || '',
        stopReason: entry.stop_reason || '',
        duration: entry.duration || 0,
        cost: entry.cost || 0,
    };
}

/**
 * Build the one-line notice that a subagent was given direction.
 * @param {object} entry the session event
 * @returns {object|null} a `subagent_steer` turn, null without a subagent id
 */
function buildSteerTurn(entry) {
    if (!entry.id) {
        return null;
    }
    return {
        role: 'subagent_steer',
        childId: entry.id,
        name: entry.name || '',
        agentName: entry.agent_name || '',
        color: entry.color || '',
        text: entry.text || '',
    };
}

/**
 * The parent's record that someone changed a subagent's brief under it.
 *
 * The parent is waiting on work it specified; if that specification changes,
 * its synthesis rests on a premise that no longer holds unless it is told.
 */
export class SubagentSteerTurn extends Component {
    static template = 'muk_ai_subagents.SubagentSteerTurn';
    static props = {
        turn: { type: Object },
        session: { type: Object },
    };
    get colorClass() {
        return colorClass(this.props.turn.color);
    }
    get label() {
        return _t(
            '%s was given more direction',
            this.props.turn.agentName || this.props.turn.name,
        );
    }
}

/** One line in the parent transcript: how many agents were delegated to. */
export class SubagentSpawnTurn extends Component {
    static template = 'muk_ai_subagents.SubagentSpawnTurn';
    static props = {
        turn: { type: Object },
        session: { type: Object },
    };
    get label() {
        const children = this.props.turn.children;
        return children.length === 1
            ? _t('Delegated to %s', children[0].name)
            : _t('Delegated to %s agents', children.length);
    }
    colorClass(child) {
        return colorClass(child.color);
    }
    onClick() {
        openStrip(this.props.session);
    }
}

/**
 * A child's outcome in the parent transcript: summary, duration, cost.
 *
 * A clean finish starts folded; anything else starts open with its stop
 * reason in view.
 */
export class SubagentResultTurn extends Component {
    static template = 'muk_ai_subagents.SubagentResultTurn';
    static props = {
        turn: { type: Object },
        session: { type: Object },
    };
    setup() {
        this.state = useState({ expanded: !this.isClean });
    }
    get isClean() {
        return isCleanStop(this.props.turn.stopReason);
    }
    get colorClass() {
        return colorClass(this.props.turn.color);
    }
    get duration() {
        return formatElapsed(this.props.turn.duration);
    }
    get cost() {
        return formatCost(this.props.turn.cost);
    }
    get warning() {
        return this.isClean ? '' : _t('Stopped early: %s', this.props.turn.stopReason);
    }
    get summaryLine() {
        return String(this.props.turn.summary || '')
            .split(/\n+/)[0]
            .trim();
    }
    get summaryHtml() {
        return this.props.session.renderMarkdown(this.props.turn.summary || '');
    }
    toggle() {
        this.state.expanded = !this.state.expanded;
    }
    onOpen() {
        const turn = this.props.turn;
        openChild(this.props.session, {
            id: turn.childId,
            name: turn.name,
            agent_name: turn.agentName,
            color: turn.color,
        });
    }
}

turnBuilders.add('delegation_start', buildSpawnTurn);
turnBuilders.add('delegation_steer', buildSteerTurn);
turnBuilders.add('delegation_result', buildResultTurn);
turnRenderers.add('subagent_spawn', SubagentSpawnTurn);
turnRenderers.add('subagent_steer', SubagentSteerTurn);
turnRenderers.add('subagent_result', SubagentResultTurn);

export { buildResultTurn, buildSpawnTurn, buildSteerTurn };
