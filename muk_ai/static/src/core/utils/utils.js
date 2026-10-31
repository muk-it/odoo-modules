import { formatDateTime } from '@web/core/l10n/dates';
import { _t } from '@web/core/l10n/translation';

const { DateTime } = luxon;

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
    done: { label: _t('Done'), icon: 'check', cls: 'mk_state_done' },
    error: { label: _t('Error'), icon: 'priority_high', cls: 'mk_state_error' },
    stopped: { label: _t('Stopped'), icon: 'stop', cls: 'mk_state_stopped' },
};

/**
 * Return the image of an agent.
 * @param {number} agentId the agent
 * @returns {string} the image route
 */
export function agentImage(agentId) {
    return `/web/image/muk_ai.agent/${agentId || 0}/image_128`;
}

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
 * Format a server timestamp as its time when it is today, else as its date.
 * @param {string} at ISO or SQL timestamp in UTC
 * @returns {string} the formatted value, empty when unparseable
 */
export function formatShortTimestamp(at) {
    const value = parseDateTime(at);
    if (!value) {
        return '';
    }
    return value.hasSame(DateTime.now(), 'day')
        ? value.toLocaleString(DateTime.TIME_SIMPLE)
        : value.toLocaleString({ day: '2-digit', month: '2-digit' });
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
