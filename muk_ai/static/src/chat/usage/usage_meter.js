// @odoo-module

import { Component, useExternalListener, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { formatInteger } from '@web/views/fields/formatters';

import { formatCost } from '@muk_ai/chat/utils';

/**
 * Context ring of a chat with a popover of its token and cost usage.
 *
 * The ring shows how full the context window is; the popover adds the input,
 * output, rounds and cost of the last turn next to the whole session's.
 */
export class AIUsageMeter extends Component {
    static template = 'muk_ai.UsageMeter';
    static props = {
        state: { type: Object },
        dropDown: { type: Boolean, optional: true },
    };

    setup() {
        this.root = useRef('root');
        this.pop = useState({ open: false });
        useExternalListener(window, 'click', (ev) => {
            if (this.pop.open && !this.root.el?.contains(ev.target)) {
                this.pop.open = false;
            }
        });
    }

    get percent() {
        const { contextWindow, lastInputTokens } = this.props.state;
        if (!contextWindow) {
            return 0;
        }
        return Math.max(
            0,
            Math.min(100, Math.round(((lastInputTokens || 0) / contextWindow) * 100)),
        );
    }

    get level() {
        if (this.percent >= 90) return 'mk_usage_red';
        if (this.percent >= 70) return 'mk_usage_amber';
        return '';
    }

    get tooltip() {
        return _t('Context window: %(tokens)s / %(window)s tokens', {
            tokens: this.formatNumber(this.props.state.lastInputTokens),
            window: this.formatNumber(this.props.state.contextWindow),
        });
    }

    get contextLabel() {
        const tokens = _t('%(tokens)s / %(window)s tokens', {
            tokens: this.formatNumber(this.props.state.lastInputTokens),
            window: this.formatNumber(this.props.state.contextWindow),
        });
        return `${tokens} (${this.percent}%)`;
    }

    get rows() {
        const state = this.props.state;
        const turn = state.turnUsage || {};
        return [
            {
                key: 'input',
                icon: 'fa-sign-in',
                label: _t('Input'),
                turn: this.formatNumber(turn.input_tokens),
                session: this.formatNumber(state.inputTokens),
            },
            {
                key: 'output',
                icon: 'fa-sign-out',
                label: _t('Output'),
                turn: this.formatNumber(turn.output_tokens),
                session: this.formatNumber(state.outputTokens),
            },
            {
                key: 'iterations',
                icon: 'fa-repeat',
                label: _t('Iterations'),
                turn: this.formatNumber(turn.iterations),
                session: this.formatNumber(state.iterationCount),
            },
            {
                key: 'cost',
                icon: 'fa-dollar',
                label: _t('Cost'),
                turn: `$${formatCost(turn.cost)}`,
                session: `$${formatCost(state.totalCost)}`,
            },
        ];
    }

    formatNumber(value) {
        return formatInteger(value || 0);
    }

    toggle() {
        this.pop.open = !this.pop.open;
    }
}
