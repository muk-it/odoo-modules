import { _t } from '@web/core/l10n/translation';
import { formatDateTime } from '@web/core/l10n/dates';

const { DateTime } = luxon;

const SECOND_MS = 1000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

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
    } catch (_e) {
        return null;
    }
    return null;
}

export function formatTimestamp(at) {
    const dt = parseDateTime(at);
    return dt ? formatDateTime(dt) : '';
}

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

export function statusLabel(status) {
    return {
        new: _t('New'),
        running: _t('Running'),
        compacting: _t('Compacting'),
        waiting: _t('Waiting'),
        waiting_schedule: _t('Scheduled'),
        done: _t('Done'),
        error: _t('Error'),
        stopped: _t('Stopped'),
    }[status] || status;
}

export function statusBadgeClass(status) {
    return STATUS_BADGE_CLASSES[status] || 'mk_state_new';
}

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

export function costTooltip(cost) {
    const value = Number(cost) || 0;
    return _t('Session cost so far: $%s (USD)', value.toFixed(6));
}

function hasOverride(state) {
    return state.approvalMode !== false && state.approvalMode !== undefined;
}

export function approvalPill(state) {
    const mode = state.effectiveApprovalMode || 'ask';
    const isOff = mode === 'off';
    const override = hasOverride(state);
    return {
        label: isOff ? _t('Bypass') : _t('Ask'),
        icon: isOff ? 'fa-bolt' : 'fa-shield',
        className: `${isOff ? 'mk_approval_bypass' : 'mk_approval_ask'}${override ? ' mk_approval_override' : ''}`,
        tooltip: isOff
            ? (override
                ? _t('Bypass (override). Click to cycle.')
                : _t('Bypass (from agent). Click to cycle.'))
            : (override
                ? _t('Ask before risky writes (override). Click to cycle.')
                : _t('Ask before risky writes (from agent). Click to cycle.')),
    };
}

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
