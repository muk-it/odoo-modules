import { Component, markup } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import {
    formatDurationSeconds,
    formatRelativeTime,
    formatTimestamp,
} from '@muk_ai/chat/utils';

const SCHEDULE_TOOL_NAMES = new Set(['schedule_resume', 'schedule_recur']);
const PROMPT_PREVIEW_MAX = 200;

function truncatePrompt(value) {
    if (!value) {
        return '';
    }
    const text = String(value);
    if (text.length <= PROMPT_PREVIEW_MAX) {
        return text;
    }
    return text.slice(0, PROMPT_PREVIEW_MAX) + '…';
}

/** Collapsible card for a single tool call: name, arguments, and result. */
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
        } catch {
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
            } catch {
                return result;
            }
        }
        try {
            return JSON.stringify(result, null, 2);
        } catch {
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
        if (/^(---\s|\+\+\+\s|@@\s)/.test(trimmed) || /^[+-]{3,}\n/.test(trimmed)) {
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
        } catch {
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
    get parsedArguments() {
        const raw = this.props.block.arguments;
        if (raw === null || raw === undefined) {
            return {};
        }
        if (typeof raw === 'string') {
            try {
                return JSON.parse(raw) || {};
            } catch {
                return {};
            }
        }
        return raw;
    }
    get parsedResult() {
        const raw = this.props.block.result;
        if (raw === null || raw === undefined) {
            return null;
        }
        if (typeof raw === 'string') {
            try {
                return JSON.parse(raw);
            } catch {
                return null;
            }
        }
        if (typeof raw === 'object') {
            return raw;
        }
        return null;
    }
    get isScheduleTool() {
        return SCHEDULE_TOOL_NAMES.has(this.props.block.name);
    }
    get scheduleSummary() {
        if (!this.isScheduleTool) {
            return null;
        }
        const name = this.props.block.name;
        const result = this.parsedResult;
        const args = this.parsedArguments;
        if (result && result.ok === false) {
            return {
                name,
                ok: false,
                error: result.error || _t('error'),
                cap: result.cap || '',
                icon: 'fa-exclamation-triangle',
            };
        }
        if (name === 'schedule_resume') {
            const resumeAt = result && result.resume_at;
            const promptFull = args.prompt || '';
            return {
                name,
                ok: true,
                icon: 'fa-clock-o',
                resumeAt,
                resumeAbsolute: formatTimestamp(resumeAt),
                resumeRelative: formatRelativeTime(resumeAt),
                promptFull,
                promptPreview: truncatePrompt(promptFull),
            };
        }
        if (name === 'schedule_recur') {
            const resumeAt = result && result.resume_at;
            const runsDone = result && result.runs_done;
            const everyText = formatDurationSeconds(args.every);
            const maxRuns = args.max_runs || (result && result.max_runs);
            const promptFull = args.prompt || '';
            return {
                name,
                ok: true,
                icon: 'fa-refresh',
                everyText,
                runsDone: runsDone || 0,
                maxRuns: maxRuns || null,
                resumeAt,
                resumeAbsolute: formatTimestamp(resumeAt),
                resumeRelative: formatRelativeTime(resumeAt),
                promptFull,
                promptPreview: truncatePrompt(promptFull),
            };
        }
        return null;
    }
    get scheduleModifierClass() {
        if (!this.isScheduleTool) {
            return '';
        }
        if (this.props.block.name === 'schedule_resume') {
            return 'mk_tool_schedule_resume';
        }
        if (this.props.block.name === 'schedule_recur') {
            return 'mk_tool_schedule_recur';
        }
        return '';
    }
    get kind() {
        const name = this.props.block.name || '';
        const result = this.props.block.result;
        const hasError = (value) => {
            if (!value) return false;
            if (typeof value === 'object')
                return Boolean(value.error || value.ok === false);
            if (typeof value === 'string') {
                try {
                    const parsed = JSON.parse(value);
                    return Boolean(parsed.error || parsed.ok === false);
                } catch {
                    return false;
                }
            }
            return false;
        };
        if (hasError(result)) return 'error';
        if (SCHEDULE_TOOL_NAMES.has(name)) return 'schedule';
        if (/^(create|update|delete|unlink|archive|call_method|write_)/.test(name))
            return 'write';
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
