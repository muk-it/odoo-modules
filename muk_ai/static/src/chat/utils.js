// @odoo-module

import { _t } from '@web/core/l10n/translation';
import { formatDateTime } from '@web/core/l10n/dates';
import { registry } from '@web/core/registry';

/**
 * Session pills an addon adds beside Approval and Effort.
 *
 * Each entry is `{sequence, build, onSelect}`: `build(state)` returns a pill
 * descriptor or nothing, and `onSelect(session, value)` acts on the choice.
 * Both surfaces draw the same list, so a pill written once appears in the
 * full page and in the floating window.
 */
export const sessionPills = registry.category('muk_ai.session_pills');

/**
 * Build the descriptors of the pills addons contribute for one session.
 * @param {object} state session UI state
 * @returns {Array} `{key, pill}` entries, those with nothing to show dropped
 */
export function extraPills(state) {
    return sessionPills
        .getEntries()
        .map(([key, entry]) => ({ key, pill: entry.build(state) }))
        .filter((entry) => entry.pill);
}

/**
 * Act on a choice made in an addon's pill.
 * @param {string} key the pill's registry key
 * @param {object} session the session handle the surface holds
 * @param {*} value what was chosen
 */
export function selectPill(key, session, value) {
    const entry = sessionPills.get(key, null);
    if (entry) {
        entry.onSelect(session, value);
    }
}

const { DateTime } = luxon;

const SECOND_MS = 1000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

/**
 * Extract a human-readable message from an RPC or JS error.
 * @param {*} error error object or value
 * @returns {string} the best available message
 */
export function formatError(error) {
    return error?.data?.message || error?.message || String(error);
}

function parseDateTime(at) {
    if (!at) {
        return null;
    }
    if (typeof at === 'object' && at.isLuxonDateTime) {
        return at.isValid ? at.toLocal() : null;
    }
    const raw = String(at);
    try {
        const iso = DateTime.fromISO(raw, { zone: 'utc' });
        if (iso.isValid) {
            return iso.toLocal();
        }
        const sql = DateTime.fromSQL(raw, { zone: 'utc' });
        if (sql.isValid) {
            return sql.toLocal();
        }
    } catch {
        return null;
    }
    return null;
}

/**
 * Format a timestamp as a localized absolute date-time string.
 * @param {*} at ISO/SQL string or Luxon DateTime
 * @returns {string} formatted date-time, or '' when unparseable
 */
export function formatTimestamp(at) {
    const dt = parseDateTime(at);
    return dt ? formatDateTime(dt) : '';
}

/**
 * Format the time until a future timestamp as a compact relative string.
 * @param {*} at ISO/SQL string or Luxon DateTime
 * @returns {string} relative time (e.g. '5m 3s'), or '' when past/invalid
 */
export function formatRelativeTime(at) {
    const dt = parseDateTime(at);
    if (!dt) {
        return '';
    }
    const diffMs = dt.toMillis() - DateTime.now().toMillis();
    if (diffMs <= 0) {
        return '';
    }
    if (diffMs < MINUTE_MS) {
        const s = Math.max(1, Math.round(diffMs / SECOND_MS));
        return _t('%ss', s);
    }
    if (diffMs < HOUR_MS) {
        const m = Math.floor(diffMs / MINUTE_MS);
        const s = Math.floor((diffMs % MINUTE_MS) / SECOND_MS);
        return _t('%sm %ss', m, s);
    }
    if (diffMs < DAY_MS) {
        const h = Math.floor(diffMs / HOUR_MS);
        const m = Math.floor((diffMs % HOUR_MS) / MINUTE_MS);
        return _t('%sh %sm', h, m);
    }
    const d = Math.floor(diffMs / DAY_MS);
    const h = Math.floor((diffMs % DAY_MS) / HOUR_MS);
    return _t('%sd %sh', d, h);
}

/**
 * Format a duration in seconds as the largest whole unit (d/h/m/s).
 * @param {*} seconds duration in seconds
 * @returns {string} formatted duration, or '' for non-positive/invalid input
 */
export function formatDurationSeconds(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) {
        return '';
    }
    const total = Math.floor(value);
    if (total % 86400 === 0) {
        return _t('%sd', total / 86400);
    }
    if (total % 3600 === 0) {
        return _t('%sh', total / 3600);
    }
    if (total % 60 === 0) {
        return _t('%sm', total / 60);
    }
    return _t('%ss', total);
}

const STATUS_BADGE_CLASSES = {
    new: 'mk_state_new',
    running: 'mk_state_running',
    compacting: 'mk_state_running',
    waiting: 'mk_state_waiting',
    waiting_schedule: 'mk_state_waiting',
    done: 'mk_state_done',
    error: 'mk_state_error',
    stopped: 'mk_state_stopped',
};

const STATUS_ICONS = {
    new: 'fa-comment-o',
    running: 'fa-spinner fa-spin',
    compacting: 'fa-spinner fa-spin',
    waiting: 'fa-hourglass-half',
    waiting_schedule: 'fa-clock-o',
    done: 'fa-check',
    error: 'fa-exclamation',
    stopped: 'fa-stop',
};

/**
 * Map a session status code to its translated label.
 * @param {string} status session status code
 * @returns {string} translated label, or the raw status when unknown
 */
export function statusLabel(status) {
    return (
        {
            new: _t('New'),
            running: _t('Running'),
            compacting: _t('Compacting'),
            waiting: _t('Waiting'),
            waiting_schedule: _t('Scheduled'),
            done: _t('Done'),
            error: _t('Error'),
            stopped: _t('Stopped'),
        }[status] || status
    );
}

/**
 * Map a session status code to its badge CSS class.
 * @param {string} status session status code
 * @returns {string} badge CSS class
 */
export function statusBadgeClass(status) {
    return STATUS_BADGE_CLASSES[status] || 'mk_state_new';
}

/**
 * Map a session status code to its FontAwesome icon class(es).
 * @param {string} status session status code
 * @returns {string} FontAwesome icon class(es)
 */
export function statusIcon(status) {
    return STATUS_ICONS[status] || 'fa-comment-o';
}

/**
 * Format a USD cost with precision scaled to its magnitude.
 * @param {*} cost cost value
 * @returns {string} formatted cost
 */
export function formatCost(cost) {
    const value = Number(cost) || 0;
    if (!value) {
        return '0';
    }
    if (value < 0.01) {
        return value.toFixed(4);
    }
    if (value < 1) {
        return value.toFixed(3);
    }
    return value.toFixed(2);
}

/**
 * Build the tooltip text showing the running session cost.
 * @param {*} cost cost value
 * @returns {string} translated tooltip text
 */
export function costTooltip(cost) {
    const value = Number(cost) || 0;
    return _t('Session cost so far: $%s (USD)', value.toFixed(6));
}

function hasOverride(state) {
    return state.approvalMode !== false && state.approvalMode !== undefined;
}

/**
 * Build the approval-mode pill descriptor (label, icon, class, tooltip).
 * @param {object} state session UI state
 * @returns {object} pill descriptor for rendering
 */
export function approvalPill(state) {
    const mode = state.effectiveApprovalMode || 'ask';
    const isOff = mode === 'off';
    const override = hasOverride(state);
    return {
        label: isOff ? _t('Bypass') : _t('Ask'),
        icon: isOff ? 'fa-bolt' : 'fa-shield',
        options: [
            {
                mode: 'ask',
                label: _t('Ask first'),
                hint: _t('Ask before risky writes'),
                icon: 'fa-shield',
                active: !isOff,
            },
            {
                mode: 'off',
                label: _t('Bypass'),
                hint: _t('Run without asking'),
                icon: 'fa-bolt',
                active: isOff,
            },
        ],
        className: `${isOff ? 'mk_approval_bypass' : 'mk_approval_ask'}${
            override ? ' mk_pill_override' : ''
        }${state.readonly ? ' disabled' : ''}`,
        tooltip: state.readonly
            ? _t('Approvals of a shared chat cannot be changed')
            : isOff
              ? override
                  ? _t('Bypass (override)')
                  : _t('Bypass (from agent)')
              : override
                ? _t('Ask before risky writes (override)')
                : _t('Ask before risky writes (from agent)'),
    };
}

/**
 * Name a reasoning effort tier for display.
 * @param {string} tier effort tier key
 * @returns {string} translated tier label, or the raw key when unknown
 */
export function effortLabel(tier) {
    return (
        {
            minimal: _t('Minimal'),
            low: _t('Low'),
            medium: _t('Medium'),
            high: _t('High'),
            xhigh: _t('Extra High'),
            max: _t('Maximum'),
        }[tier] ||
        tier ||
        ''
    );
}

/**
 * State what a reasoning effort tier buys and what it costs.
 * @param {string} tier effort tier key
 * @returns {string} translated one-line hint, empty when the tier is unknown
 */
function effortHint(tier) {
    return (
        {
            minimal: _t('Answers immediately, barely thinks'),
            low: _t('Fastest, everyday questions'),
            medium: _t('Balanced'),
            high: _t('Hard analysis · costs more'),
            xhigh: _t('Long chains of reasoning · costs much more'),
            max: _t('Everything the model has · slowest'),
        }[tier] || ''
    );
}

/**
 * Build the reasoning-effort pill descriptor, or null when the model has none.
 *
 * An override the model stopped accepting reads as no override at all: the
 * pill then shows what the turn will really run on rather than a ring over a
 * tier the session cannot spend.
 * @param {object} state session UI state
 * @returns {object|null} pill descriptor, or null when there is nothing to pick
 */
export function effortPill(state) {
    const tiers = state.reasoningEffortOptions || [];
    if (!tiers.length) {
        return null;
    }
    const override = tiers.includes(state.reasoningEffort)
        ? state.reasoningEffort
        : false;
    const effective = state.effectiveReasoningEffort;
    const agent = state.agentReasoningEffort;
    return {
        label: effective ? effortLabel(effective) : _t('Default'),
        // The inherit row is just the first option, so every surface can render
        // the menu as one loop and clearing reads as picking a tier.
        options: [
            {
                tier: false,
                label: agent
                    ? _t('Agent default — %s', effortLabel(agent))
                    : _t('Agent default'),
                hint: '',
                active: !override,
            },
            ...tiers.map((tier) => ({
                tier,
                label: effortLabel(tier),
                hint: effortHint(tier),
                // Checked means "pinned to this chat", not "what the turn
                // happens to run on" — otherwise inheriting a tier ticks both
                // the agent default row and the tier it resolves to.
                active: tier === override,
            })),
        ],
        className: override ? 'mk_pill_override' : '',
        tooltip: override
            ? _t('How hard the model thinks (override)')
            : _t('How hard the model thinks (from agent)'),
    };
}

/**
 * Pick the composer placeholder text for the current session status.
 * @param {object} state session UI state
 * @param {string} defaultText fallback placeholder when idle
 * @returns {string} placeholder text
 */
export function inputPlaceholder(state, defaultText) {
    if (state.status === 'waiting') {
        const kind = (state.pendingAsk || {}).kind;
        return kind === 'approval'
            ? _t('Approve or reject to continue…')
            : _t('Type your answer…');
    }
    if (state.status === 'waiting_schedule') {
        return _t('Scheduled. Type to wake the agent…');
    }
    if (state.status === 'running') {
        return _t('Stop to interrupt…');
    }
    if (state.status === 'compacting') {
        return _t('Compacting in background — message will queue…');
    }
    return defaultText;
}
