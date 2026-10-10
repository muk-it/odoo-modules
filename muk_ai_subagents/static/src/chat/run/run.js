import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import {
    describeToolBlock,
    hiddenToolBlocks,
    toolBlockDecorators,
    toolPayload,
} from '@muk_ai/chat/session/turns';
import {
    sessionEventHandlers,
    sessionStateFields,
} from '@muk_ai/chat/session/use_ai_session';
import { patchChatSurfaces } from '@muk_ai/chat/surfaces';
import { chatLists } from '@muk_ai/chat/utils';
import { aiSessionChatAction } from '@muk_ai/webclient/notification/session_redirect';

export const DELEGATE_TOOL = 'delegate';

const URGENCY = ['needs_you', 'working', 'failed', 'stopped', 'done'];
const EARLY_STOPS = ['budget', 'no_progress', 'max_iterations', 'error'];
const received = new WeakMap();

/**
 * Tell what a subagent of the run needs from the user, if anything.
 * @param {object} child a roster entry
 * @returns {string} `needs_you`, `working`, `failed`, `stopped` or `done`
 */
export function childStatus(child) {
    if (child.state === 'waiting') {
        return 'needs_you';
    }
    if (!['done', 'error', 'stopped'].includes(child.state)) {
        return 'working';
    }
    if (child.state === 'error' || EARLY_STOPS.includes(child.stop_reason)) {
        return 'failed';
    }
    return child.state === 'stopped' ? 'stopped' : 'done';
}

/**
 * Order subagents by what the user has to act on first.
 * @param {Array} children roster entries
 * @returns {Array} the entries, waiting first, then working, ended last
 */
export function byUrgency(children) {
    const rank = (child) => URGENCY.indexOf(childStatus(child));
    return [...children].sort((a, b) => rank(a) - rank(b) || a.id - b.id);
}

/**
 * Format a duration for a row of the run.
 * @param {number} seconds the duration
 * @returns {string} `12s`, `4m 05s` or `1h 03m`, empty for nothing
 */
export function formatElapsed(seconds) {
    const total = Math.floor(Number(seconds) || 0);
    const pad = (value) => String(value).padStart(2, '0');
    if (total <= 0) {
        return '';
    }
    if (total < 60) {
        return _t('%ss', total);
    }
    if (total < 3600) {
        return _t('%sm %ss', Math.floor(total / 60), pad(total % 60));
    }
    return _t(
        '%sh %sm',
        Math.floor(total / 3600),
        pad(Math.floor((total % 3600) / 60)),
    );
}

/**
 * Return how long a subagent has run, counting on from the roster it came in
 * while it works.
 * @param {object} child a roster entry
 * @param {object} run the roster
 * @param {number} now the current time in milliseconds
 * @returns {number} seconds
 */
export function liveElapsed(child, run, now) {
    if (!received.has(run)) {
        received.set(run, now);
    }
    const ticking = ['working', 'needs_you'].includes(childStatus(child));
    return child.elapsed + (ticking ? (now - received.get(run)) / 1000 : 0);
}

/**
 * Say in a few words what a working subagent is doing, the way the
 * transcript labels the same tool call.
 * @param {object} child a roster entry
 * @returns {string} the activity
 */
export function activityText(child) {
    const activity = child.activity;
    if (child.repeating) {
        return _t('Repeating the same call');
    }
    if (activity?.kind === 'tool_call') {
        const block = {
            type: 'tool',
            name: activity.name,
            arguments: activity.arguments,
        };
        for (const decorate of toolBlockDecorators.getAll()) {
            decorate(block, activity);
        }
        return block.label || activity.name;
    }
    return activity?.kind === 'text' ? _t('Writing the report') : _t('Thinking');
}

/**
 * Return the first line of a report that reads as text, without its markdown.
 * @param {string} report the report
 * @returns {string} the line, empty for no report
 */
export function reportLine(report) {
    const lines = (report || '').split(/\n+/).map((line) => line.trim());
    const words = lines.filter((text) => /\w/.test(text));
    const line = words.find((text) => !text.startsWith('|')) || words[0] || '';
    return line
        .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
        .replace(/[|*_`#>]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

/**
 * Say why a subagent ended, when it did not simply finish.
 * @param {object} child a roster entry
 * @returns {string} the reason, empty for a clean finish
 */
export function endText(child) {
    const reasons = {
        budget: _t('Stopped at the budget'),
        no_progress: _t('Stopped for repeating itself'),
        max_iterations: _t('Stopped at the round limit'),
        stopped: _t('Stopped'),
    };
    if (child.stop_reason in reasons) {
        return reasons[child.stop_reason];
    }
    return child.state === 'error' ? child.error || _t('Failed') : '';
}

/**
 * Say what a waiting subagent asks of the user.
 * @param {object} child a roster entry
 * @returns {string} the question, or that an approval is pending
 */
export function askText(child) {
    if (child.ask?.kind === 'approval') {
        return _t('Needs your approval');
    }
    return child.ask?.text || _t('Needs your answer');
}

/**
 * Open a chat of the run in a window beside the one showing it, or in its
 * place on a small screen.
 * @param {object} services the `action`, `ui` and `muk_ai.chat_window` services
 * @param {number} id the chat
 */
export function openChat(services, id) {
    if (services.ui.isSmall) {
        services.action.doAction(aiSessionChatAction(id), {
            stackPosition: 'replaceCurrentAction',
        });
    } else {
        services.chatWindow.open(id);
    }
}

for (const field of ['subagents', 'subagent_of']) {
    sessionStateFields.add(`muk_ai_subagents.${field}`, {
        field,
        apply: (state, record) => {
            state[field] = record[field] || null;
        },
    });
}

sessionEventHandlers.add('subagent_update', (payload, { state }) => {
    state.subagents = payload;
});

toolBlockDecorators.add('muk_ai_subagents.delegate', (block) => {
    if (block.name === DELEGATE_TOOL) {
        describeToolBlock(block, {
            kind: 'delegate',
            icon: () => 'fa-sitemap',
            label: () => _t('Delegate'),
        });
    }
});

hiddenToolBlocks.add(
    'muk_ai_subagents.delegate',
    (block) => block.name === DELEGATE_TOOL && !toolPayload(block.result)?.error,
);

patchChatSurfaces(() => ({
    get inputPlaceholder() {
        const state = this.session.state;
        return state.status === 'waiting' && state.pendingAsk?.kind === 'children'
            ? _t('Subagents are working, a message waits for their reports...')
            : super.inputPlaceholder;
    },
}));

patch(chatLists, {
    get domain() {
        return [...super.domain, ['parent_session_id', '=', false]];
    },
});
