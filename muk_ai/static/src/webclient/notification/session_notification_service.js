import { _t } from '@web/core/l10n/translation';
import { deserializeDateTime } from '@web/core/l10n/dates';
import { registry } from '@web/core/registry';

/** Drop replayed notifications older than this; the inbox keeps the durable copy. */
export const NOTIFICATION_FRESHNESS_MS = 2 * 60 * 1000;

/**
 * Return the age in milliseconds of a server-stamped notification, or ``null``.
 *
 * @param {string|undefined} at Server datetime string (naive UTC) of emission.
 * @param {number} now Current epoch milliseconds.
 * @returns {number|null} Age in milliseconds, or ``null`` when ``at`` is unusable.
 */
export function notificationAgeMs(at, now) {
    if (!at) {
        return null;
    }
    try {
        const emitted = deserializeDateTime(at);
        const ms = emitted?.toMillis?.();
        return Number.isFinite(ms) ? now - ms : null;
    } catch {
        return null;
    }
}

/**
 * Decide whether a session notification should pop as a toast in this tab.
 *
 * Suppresses notifications for the session already open and active here, for
 * background or hidden tabs (only the visible tab toasts, which also dedupes
 * across tabs), and for stale replays from the bus backlog. A missing or
 * unparsable timestamp is treated as fresh so older payloads still show.
 *
 * @param {object} payload The ``muk_ai.session_notification`` bus payload.
 * @param {object} ctx Decision context.
 * @param {boolean} ctx.isActive Whether the session is open and active here.
 * @param {boolean} ctx.isVisible Whether this tab is currently visible.
 * @param {number} ctx.now Current epoch milliseconds.
 * @param {number} [ctx.freshnessMs] Maximum tolerated age before dropping.
 * @returns {boolean} ``true`` when the toast should be shown.
 */
export function shouldShowNotification(
    payload,
    { isActive, isVisible, now, freshnessMs = NOTIFICATION_FRESHNESS_MS },
) {
    if (!payload || !payload.session_id) {
        return false;
    }
    if (isActive || !isVisible) {
        return false;
    }
    const age = notificationAgeMs(payload.at, now);
    if (age !== null && age > freshnessMs) {
        return false;
    }
    return true;
}

export const sessionNotificationService = {
    dependencies: ['action', 'bus_service', 'notification', 'orm'],
    start(env) {
        const active = new Map();
        const closers = new Map();
        function closeForSession(sessionId) {
            const set = closers.get(sessionId);
            if (!set) {
                return;
            }
            for (const close of set) {
                try {
                    close();
                } catch {
                    /* ignore */
                }
            }
            closers.delete(sessionId);
        }
        function dismissInbox(sessionId) {
            env.services.orm.silent
                .call('muk_ai.session', 'dismiss_notifications', [[sessionId]])
                .catch(() => {});
        }
        function markActive(sessionId) {
            if (!sessionId) {
                return;
            }
            active.set(sessionId, (active.get(sessionId) || 0) + 1);
            closeForSession(sessionId);
            dismissInbox(sessionId);
        }
        function markInactive(sessionId) {
            if (!sessionId) {
                return;
            }
            const count = (active.get(sessionId) || 0) - 1;
            if (count <= 0) {
                active.delete(sessionId);
            } else {
                active.set(sessionId, count);
            }
        }
        function onNotification(payload) {
            const show = shouldShowNotification(payload, {
                isActive: active.has(payload?.session_id),
                isVisible: document.visibilityState === 'visible',
                now: Date.now(),
            });
            if (!show) {
                return;
            }
            const type =
                payload.state === 'error'
                    ? 'danger'
                    : payload.state === 'waiting'
                      ? 'warning'
                      : 'success';
            const close = env.services.notification.add(
                payload.message || payload.title || _t('AI session updated'),
                {
                    type,
                    title: payload.title || _t('AI Session'),
                    sticky: payload.state !== 'done',
                    className: 'mk_ai_notification',
                    buttons: [
                        {
                            name: _t('Open Chat'),
                            primary: true,
                            onClick: () => {
                                env.services.action.doAction({
                                    type: 'ir.actions.client',
                                    tag: 'muk_ai.chat',
                                    params: { session_id: payload.session_id },
                                });
                            },
                        },
                    ],
                },
            );
            if (payload.state !== 'done') {
                let set = closers.get(payload.session_id);
                if (!set) {
                    set = new Set();
                    closers.set(payload.session_id, set);
                }
                set.add(close);
            }
        }
        env.services.bus_service.subscribe(
            'muk_ai.session_notification',
            onNotification,
        );
        return { markActive, markInactive };
    },
};

registry
    .category('services')
    .add('muk_ai.session_notification', sessionNotificationService);
