/** @odoo-module */

import { Component } from '@odoo/owl';

export class ToolCard extends Component {
    static template = 'muk_ai.ToolCard';
    static props = {
        block: { type: Object },
        expanded: { type: Boolean, optional: true },
        streaming: { type: Boolean, optional: true },
        onToggle: { type: Function, optional: true },
    };

    static defaultProps = {
        expanded: false,
        streaming: false,
    };

    formatArgs(args) {
        if (args === null || args === undefined) {
            return '';
        }
        if (typeof args === 'string') {
            return args;
        }
        try {
            return JSON.stringify(args, null, 2);
        } catch (_err) {
            return String(args);
        }
    }

    formatResult(result) {
        if (result === null || result === undefined) {
            return '';
        }
        if (typeof result === 'string') {
            try {
                return JSON.stringify(JSON.parse(result), null, 2);
            } catch (_err) {
                return result;
            }
        }
        try {
            return JSON.stringify(result, null, 2);
        } catch (_err) {
            return String(result);
        }
    }

    get summary() {
        const raw = this.props.block.arguments
            ? this.formatArgs(this.props.block.arguments).replace(/\s+/g, ' ')
            : '';
        return raw.length > 60 ? raw.slice(0, 60) + '…' : raw;
    }

    onHeadClick() {
        if (this.props.streaming || !this.props.onToggle) {
            return;
        }
        this.props.onToggle(this.props.block.callId);
    }
}
