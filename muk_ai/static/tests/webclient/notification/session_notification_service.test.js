import { after, describe, expect, test } from '@odoo/hoot';
import { patchTranslations } from '@web/../tests/web_test_helpers';

import { sessionNotificationService } from '@muk_ai/webclient/notification/session_notification_service';

describe.current.tags('muk_ai');
patchTranslations();

/**
 * Pin ``document.visibilityState`` for the duration of the current test.
 * @param {string} value visibility state the service should observe
 */
function mockTabVisibility(value) {
    Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        get: () => value,
    });
    after(() => delete document.visibilityState);
}

/**
 * Start the notification service against recording stubs of its dependencies.
 * @returns {object} the service API plus the recorded side effects and a bus emitter
 */
function startService() {
    const actions = [];
    const ormCalls = [];
    const toasts = [];
    let handler = null;
    const env = {
        services: {
            action: {
                doAction: (action) => {
                    actions.push(action);
                    return Promise.resolve();
                },
            },
            bus_service: {
                subscribe: (channel, callback) => {
                    if (channel === 'muk_ai.session_notification') {
                        handler = callback;
                    }
                },
            },
            notification: {
                add: (message, options) => {
                    const toast = {
                        message: String(message),
                        title: String(options.title),
                        type: options.type,
                        sticky: options.sticky,
                        buttons: options.buttons,
                        closed: false,
                    };
                    toasts.push(toast);
                    return () => {
                        toast.closed = true;
                    };
                },
            },
            orm: {
                silent: {
                    call: (model, method, args) => {
                        ormCalls.push({ model, method, args });
                        return Promise.resolve();
                    },
                },
            },
        },
    };
    const api = sessionNotificationService.start(env);
    return {
        api,
        actions,
        ormCalls,
        toasts,
        emit: (payload) => handler(payload),
    };
}

/**
 * Build a ``muk_ai.session_notification`` bus payload.
 * @param {object} [extra] fields overriding the defaults
 * @returns {object} the bus payload
 */
function notify(extra = {}) {
    return { session_id: 7, state: 'done', message: 'Run finished', ...extra };
}

test('a session notification toasts with an Open Chat button for that session', () => {
    mockTabVisibility('visible');
    const { emit, toasts, actions } = startService();
    emit(notify({ title: 'Report ready' }));
    expect(toasts).toHaveLength(1);
    expect(toasts[0].message).toBe('Run finished');
    expect(toasts[0].title).toBe('Report ready');
    expect(toasts[0].buttons[0].name.toString()).toBe('Open Chat');
    toasts[0].buttons[0].onClick();
    expect(actions).toEqual([
        {
            type: 'ir.actions.client',
            tag: 'muk_ai.chat',
            params: { session_id: 7 },
        },
    ]);
});

test('a notification without a message falls back to its title', () => {
    mockTabVisibility('visible');
    const { emit, toasts } = startService();
    emit({ session_id: 7, state: 'done', title: 'Report ready' });
    expect(toasts[0].message).toBe('Report ready');
});

test('the toast severity follows the session state', () => {
    mockTabVisibility('visible');
    const { emit, toasts } = startService();
    emit(notify({ state: 'error' }));
    emit(notify({ state: 'waiting' }));
    emit(notify({ state: 'done' }));
    expect(toasts.map((t) => t.type)).toEqual(['danger', 'warning', 'success']);
});

test('only a finished session produces a self-dismissing toast', () => {
    mockTabVisibility('visible');
    const { emit, toasts } = startService();
    emit(notify({ state: 'done' }));
    emit(notify({ state: 'running' }));
    expect(toasts.map((t) => t.sticky)).toEqual([false, true]);
});

test('opening a session closes its pending toasts and clears its inbox', () => {
    mockTabVisibility('visible');
    const { api, emit, toasts, ormCalls } = startService();
    emit(notify({ state: 'error' }));
    emit(notify({ state: 'waiting' }));
    emit(notify({ session_id: 9, state: 'error' }));
    api.markActive(7);
    expect(toasts.map((t) => t.closed)).toEqual([true, true, false]);
    expect(ormCalls).toEqual([
        {
            model: 'muk_ai.session',
            method: 'dismiss_notifications',
            args: [[7]],
        },
    ]);
});

test('a finished toast is left alone when its session is opened', () => {
    mockTabVisibility('visible');
    const { api, emit, toasts } = startService();
    emit(notify({ state: 'done' }));
    api.markActive(7);
    expect(toasts[0].closed).toBe(false);
});

test('the last window closing re-enables notifications for the session', () => {
    mockTabVisibility('visible');
    const { api, emit, toasts } = startService();
    api.markActive(7);
    api.markActive(7);
    emit(notify({ state: 'error' }));
    expect(toasts).toHaveLength(0);

    api.markInactive(7);
    emit(notify({ state: 'error' }));
    expect(toasts).toHaveLength(0);

    api.markInactive(7);
    emit(notify({ state: 'error' }));
    expect(toasts).toHaveLength(1);
});

test('markActive and markInactive ignore a missing session id', () => {
    mockTabVisibility('visible');
    const { api, emit, toasts, ormCalls } = startService();
    api.markActive(undefined);
    api.markInactive(null);
    expect(ormCalls).toEqual([]);
    emit(notify({ state: 'error' }));
    expect(toasts).toHaveLength(1);
});

test('a hidden tab stays silent so only the visible one toasts', () => {
    mockTabVisibility('hidden');
    const { emit, toasts } = startService();
    emit(notify({ state: 'error' }));
    expect(toasts).toHaveLength(0);
});
