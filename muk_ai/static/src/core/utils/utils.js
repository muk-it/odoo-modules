import { formatDateTime } from '@web/core/l10n/dates';
import { _t } from '@web/core/l10n/translation';

const { DateTime } = luxon;

const MINUTE_S = 60;
const HOUR_S = 60 * MINUTE_S;
const DAY_S = 24 * HOUR_S;

/**
 * Label, Material Symbols icon and colour class of every session state.
 */
const STATUS = {
    new: { label: _t('New'), icon: 'chat_bubble', cls: 'mk_state_new' },
    running: {
        label: _t('Running'),
        icon: 'progress_activity',
        cls: 'mk_state_running',
        spin: true,
    },
    compacting: {
        label: _t('Compacting'),
        icon: 'progress_activity',
        cls: 'mk_state_running',
        spin: true,
    },
    waiting: { label: _t('Waiting'), icon: 'hourglass_top', cls: 'mk_state_waiting' },
    waiting_schedule: {
        label: _t('Scheduled'),
        icon: 'schedule',
        cls: 'mk_state_waiting',
    },
    done: { label: _t('Done'), icon: 'check', cls: 'mk_state_done' },
    error: { label: _t('Error'), icon: 'priority_high', cls: 'mk_state_error' },
    stopped: { label: _t('Stopped'), icon: 'stop', cls: 'mk_state_stopped' },
};

/**
 * Describe a session state for display.
 * @param {string} status session state code
 * @returns {object} `{label, icon, cls, spin}`, the new state for an unknown code
 */
export function statusInfo(status) {
    return STATUS[status] || { ...STATUS.new, label: status || STATUS.new.label };
}

/**
 * Extract a human-readable message from an RPC or JS error.
 * @param {*} error error object or value
 * @returns {string} the best available message
 */
export function formatError(error) {
    return error?.data?.message || error?.message || String(error);
}

/**
 * Parse a server timestamp, ISO or SQL, given in UTC.
 * @param {string} at the timestamp
 * @returns {object|null} a local Luxon DateTime, null when unparseable
 */
function parseDateTime(at) {
    if (!at) {
        return null;
    }
    const raw = String(at);
    const parsed = DateTime.fromISO(raw, { zone: 'utc' });
    const value = parsed.isValid ? parsed : DateTime.fromSQL(raw, { zone: 'utc' });
    return value.isValid ? value.toLocal() : null;
}

/**
 * Format a server timestamp as a localized date-time.
 * @param {string} at ISO or SQL timestamp in UTC
 * @returns {string} the formatted value, empty when unparseable
 */
export function formatTimestamp(at) {
    const value = parseDateTime(at);
    return value ? formatDateTime(value) : '';
}

/**
 * Format the time left until a server timestamp, in its two largest units.
 * @param {string} at ISO or SQL timestamp in UTC
 * @returns {string} e.g. `5m 3s`, empty when past or unparseable
 */
export function formatRelativeTime(at) {
    const value = parseDateTime(at);
    const left = value ? Math.round((value.toMillis() - Date.now()) / 1000) : 0;
    if (left <= 0) {
        return '';
    }
    if (left < MINUTE_S) {
        return _t('%ss', left);
    }
    if (left < HOUR_S) {
        return _t('%sm %ss', Math.floor(left / MINUTE_S), left % MINUTE_S);
    }
    if (left < DAY_S) {
        return _t(
            '%sh %sm',
            Math.floor(left / HOUR_S),
            Math.floor((left % HOUR_S) / MINUTE_S),
        );
    }
    return _t('%sd %sh', Math.floor(left / DAY_S), Math.floor((left % DAY_S) / HOUR_S));
}

/**
 * Format a USD cost with a precision scaled to its magnitude.
 * @param {*} cost the cost
 * @returns {string} the formatted cost
 */
export function formatCost(cost) {
    const value = Number(cost) || 0;
    if (!value) {
        return '0';
    }
    return value.toFixed(value < 0.01 ? 4 : value < 1 ? 3 : 2);
}

/**
 * Return the URL of a user's avatar.
 * @param {number} userId the user
 * @returns {string} the image route
 */
export function avatarUrl(userId) {
    return `/web/image/res.users/${userId}/avatar_128`;
}
