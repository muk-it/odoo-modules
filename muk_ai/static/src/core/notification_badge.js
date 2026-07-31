import { onWillStart, onWillUnmount, useState } from '@odoo/owl';

import { useService } from '@web/core/utils/hooks';

/**
 * Track the current user's unread AI sessions.
 *
 * Loads the badge once before mount and keeps it live via the
 * "muk_ai.notification_badge" bus channel.
 *
 * @returns {{count: number, unreadIds: number[], spaceUnread: object, isUnread: (sessionId: number) => boolean}}
 */
export function useNotificationBadge() {
    const orm = useService('orm');
    const bus = useService('bus_service');
    const badge = useState({
        count: 0,
        unreadIds: [],
        spaceUnread: {},
        isUnread: (sessionId) => badge.unreadIds.includes(sessionId),
    });
    let pushed = false;
    const apply = (payload) => {
        if (!payload || !Array.isArray(payload.session_ids)) {
            return;
        }
        badge.unreadIds = payload.session_ids;
        badge.spaceUnread = payload.space_unread || {};
        badge.count =
            typeof payload.count === 'number'
                ? payload.count
                : payload.session_ids.length;
    };
    const applyPush = (payload) => {
        pushed = true;
        apply(payload);
    };
    onWillStart(async () => {
        let initial = { count: 0, session_ids: [] };
        try {
            initial = await orm.call('muk_ai.session', 'notification_badge', []);
        } catch {
            // keep the empty badge when the initial load fails
        }
        if (!pushed) {
            apply(initial);
        }
    });
    bus.subscribe('muk_ai.notification_badge', applyPush);
    onWillUnmount(() => bus.unsubscribe('muk_ai.notification_badge', applyPush));
    return badge;
}
