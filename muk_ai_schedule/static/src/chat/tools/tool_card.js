import { _t } from '@web/core/l10n/translation';

import { toolBlockDecorators } from '@muk_ai/chat/session/turns';
import {
    formatDurationSeconds,
    formatRelativeTime,
    formatTimestamp,
} from '@muk_ai/chat/utils';

const PROMPT_PREVIEW_MAX = 200;

function parseJson(value) {
    if (typeof value !== 'string') {
        return value || null;
    }
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function truncatePrompt(value) {
    const text = String(value || '');
    return text.length > PROMPT_PREVIEW_MAX
        ? text.slice(0, PROMPT_PREVIEW_MAX) + '…'
        : text;
}

function whenText(resumeAt) {
    const absolute = formatTimestamp(resumeAt);
    const relative = formatRelativeTime(resumeAt);
    return relative ? `${absolute} (${relative})` : absolute;
}

function resumeBand(args, result) {
    const parts = [_t('Paused — resumes %s', whenText(result?.resume_at))];
    if (args.prompt) {
        parts.push(_t('Will ask: "%s"', truncatePrompt(args.prompt)));
    }
    return parts.join(' · ');
}

function recurBand(args, result) {
    const maxRuns = args.max_runs || result?.max_runs || '∞';
    const parts = [
        _t(
            'Every %s · run %s/%s',
            formatDurationSeconds(args.every),
            result?.runs_done || 0,
            maxRuns,
        ),
    ];
    if (result?.resume_at) {
        parts.push(_t('next %s', whenText(result.resume_at)));
    }
    if (args.prompt) {
        parts.push(_t('Each fire asks: "%s"', truncatePrompt(args.prompt)));
    }
    return parts.join(' · ');
}

const SCHEDULE_TOOLS = {
    schedule_resume: { kind: 'schedule_resume', icon: 'fa-clock-o', band: resumeBand },
    schedule_recur: { kind: 'schedule_recur', icon: 'fa-refresh', band: recurBand },
};

/**
 * Give a schedule tool block its kind, icon and summary band.
 *
 * The tool result arrives after decoration, so icon and band are getters that
 * read the block's current result each time the card renders.
 * @param {object} block the tool block being built
 */
function decorateScheduleBlock(block) {
    const tool = SCHEDULE_TOOLS[block.name];
    if (!tool) {
        return;
    }
    block.kind = tool.kind;
    Object.defineProperties(block, {
        icon: {
            enumerable: true,
            get() {
                const result = parseJson(this.result);
                return result?.ok === false ? 'fa-exclamation-triangle' : tool.icon;
            },
        },
        band: {
            enumerable: true,
            get() {
                const result = parseJson(this.result);
                if (result?.ok === false) {
                    const error = result.error || _t('error');
                    return result.cap ? `${error}: ${result.cap}` : error;
                }
                return tool.band(parseJson(this.arguments) || {}, result);
            },
        },
    });
}

toolBlockDecorators.add('muk_ai_schedule.schedule_tools', decorateScheduleBlock);
