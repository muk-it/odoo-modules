import { _t } from '@web/core/l10n/translation';
import { formatDateTime } from '@web/core/l10n/dates';

const { DateTime } = luxon;

export function formatError(error) {
    return error?.data?.message || error?.message || String(error);
}

export function formatTimestamp(at) {
    if (!at) {
        return '';
    }
    try {
        const dt = DateTime.fromISO(at, { zone: 'utc' }).toLocal();
        return dt.isValid ? formatDateTime(dt) : '';
    } catch (_e) {
        return '';
    }
}

const STATUS_BADGE_CLASSES = {
    new: 'mk_state_new',
    running: 'mk_state_running',
    compacting: 'mk_state_running',
    waiting: 'mk_state_waiting',
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
    if (state.status === 'running') {
        return _t('Stop to interrupt…');
    }
    if (state.status === 'compacting') {
        return _t('Compacting…');
    }
    return defaultText;
}
