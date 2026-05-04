import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

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
                try { close(); } catch (_e) {}
            }
            closers.delete(sessionId);
        }
        function dismissInbox(sessionId) {
            env.services.orm.silent.call(
                'muk_ai.session', 'dismiss_notifications', [[sessionId]],
            ).catch(() => {});
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
            if (!payload || !payload.session_id) {
                return;
            }
            if (active.has(payload.session_id)) {
                return;
            }
            const type = payload.state === 'error'
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
                    buttons: [{
                        name: _t('Open Chat'),
                        primary: true,
                        onClick: () => {
                            env.services.action.doAction({
                                type: 'ir.actions.client',
                                tag: 'muk_ai.chat',
                                params: { session_id: payload.session_id },
                            });
                        },
                    }],
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
            'muk_ai.session_notification', onNotification,
        );
        return { markActive, markInactive };
    },
};

registry.category('services').add(
    'muk_ai.session_notification', sessionNotificationService,
);
