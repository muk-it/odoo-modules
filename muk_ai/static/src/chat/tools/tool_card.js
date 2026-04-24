import { Component, markup } from '@odoo/owl';

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
    get resultLang() {
        const raw = this.props.block.result;
        if (typeof raw !== 'string') {
            return 'json';
        }
        const trimmed = raw.trimStart();
        if (/^(---\s|\+\+\+\s|@@\s)/.test(trimmed) || /^[\+\-]{3,}\n/.test(trimmed)) {
            return 'diff';
        }
        return 'json';
    }
    highlight(text, lang) {
        const Prism = window.Prism;
        const grammar = Prism && Prism.languages[lang];
        if (!grammar) {
            return null;
        }
        try {
            return markup(Prism.highlight(text, grammar, lang));
        } catch (_err) {
            return null;
        }
    }
    get renderedArgs() {
        const text = this.formatArgs(this.props.block.arguments);
        return this.highlight(text, 'json') ?? text;
    }
    get renderedResult() {
        const text = this.formatResult(this.props.block.result);
        return this.highlight(text, this.resultLang) ?? text;
    }
    get kind() {
        const name = this.props.block.name || '';
        const result = this.props.block.result;
        const hasError = (value) => {
            if (!value) return false;
            if (typeof value === 'object') return Boolean(value.error);
            if (typeof value === 'string') {
                try { return Boolean(JSON.parse(value).error); } catch (_e) { return false; }
            }
            return false;
        };
        if (hasError(result)) return 'error';
        if (/^(create|update|delete|unlink|archive|call_method|write_)/.test(name)) return 'write';
        if (/^(open_|show_notification)/.test(name)) return 'nav';
        if (/^(search|read|get_|list_|fields_|count_)/.test(name)) return 'read';
        return 'default';
    }
    onHeadClick() {
        if (this.props.streaming || !this.props.onToggle) {
            return;
        }
        this.props.onToggle(this.props.block.callId);
    }
}
