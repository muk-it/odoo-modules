import { Component, markup, proxy, t, useProps } from '@odoo/owl';

import { highlightCode } from '@muk_ai/core/markdown/markdown';
import { toolBlockHasError, toolPayload } from '@muk_ai/core/session/turns';

const CHIP_LIMIT = 4;
const KINDS = [
    ['write', /^(create|update|delete|unlink|archive|call_method|write_)/],
    ['nav', /^(open_|show_notification)/],
    ['read', /^(search|read|get_|list_|fields_|count_)/],
];

/**
 * Pretty-print a tool payload, leaving text that is not JSON as it is.
 * @param {*} value the raw arguments or result
 * @returns {string} the text to show
 */
function pretty(value) {
    if (value === null || value === undefined) {
        return '';
    }
    const parsed = toolPayload(value);
    return parsed && typeof parsed === 'object'
        ? JSON.stringify(parsed, null, 2)
        : String(value);
}

/** Collapsible card of one tool call: its name, arguments and result. */
export class ToolCard extends Component {
    static template = 'muk_ai.ToolCard';
    props = useProps({
        block: t.object(),
        expanded: t.boolean().optional(false),
        streaming: t.boolean().optional(false),
        onToggle: t.function().optional(),
    });
    get hasError() {
        return toolBlockHasError(this.props.block);
    }
    get kind() {
        const { kind, name = '' } = this.props.block;
        if (kind || this.hasError) {
            return kind || 'error';
        }
        return KINDS.find(([, pattern]) => pattern.test(name))?.[0] || 'default';
    }
    get resultLang() {
        const raw = this.props.block.result;
        const head = typeof raw === 'string' ? raw.trimStart() : '';
        return /^(---\s|\+\+\+\s|@@\s)/.test(head) || /^[+-]{3,}\n/.test(head)
            ? 'diff'
            : 'json';
    }
    /**
     * Highlight a payload with Prism when it is loaded.
     * @param {*} value the raw arguments or result
     * @param {string} lang the Prism language
     * @returns {object|string} highlighted markup, or the plain text
     */
    highlight(value, lang) {
        const text = pretty(value);
        const html = highlightCode(text, lang);
        return html ? markup(html) : text;
    }
    onHeadClick() {
        if (!this.props.streaming) {
            this.props.onToggle?.(this.props.block.callId);
        }
    }
}

/** Collapsible cluster of consecutive tool calls of one assistant turn. */
export class ToolGroup extends Component {
    static template = 'muk_ai.ToolGroup';
    static components = { ToolCard };
    props = useProps({
        tools: t.array(),
        compact: t.boolean().optional(false),
        isExpanded: t.function(),
        onToggle: t.function(),
    });
    state = proxy({ expanded: false });
    get errors() {
        return this.props.tools.filter((tool) => toolBlockHasError(tool.block)).length;
    }
    get chips() {
        return this.props.tools
            .slice(0, CHIP_LIMIT)
            .map((tool) => tool.block.label || tool.block.name);
    }
}
