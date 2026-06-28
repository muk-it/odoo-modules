import { describe, expect, test } from '@odoo/hoot';
import { serializeDateTime } from '@web/core/l10n/dates';

import {
    NOTIFICATION_FRESHNESS_MS,
    notificationAgeMs,
    shouldShowNotification,
} from '@muk_ai/webclient/notification/session_notification_service';

describe.current.tags('muk_ai');

const EMITTED = luxon.DateTime.utc(2026, 6, 28, 7, 0, 0);
const EMITTED_MS = EMITTED.toMillis();

function serverTime() {
    return serializeDateTime(EMITTED);
}

function payload(extra = {}) {
    return { session_id: 7, state: 'done', at: serverTime(), ...extra };
}

function ctx(extra = {}) {
    return { isActive: false, isVisible: true, now: EMITTED_MS, ...extra };
}

// ----------------------------------------------------------
// notificationAgeMs
// ----------------------------------------------------------

test('notificationAgeMs: null for a missing or unparsable timestamp', () => {
    expect(notificationAgeMs(undefined, EMITTED_MS)).toBe(null);
    expect(notificationAgeMs('', EMITTED_MS)).toBe(null);
    expect(notificationAgeMs('not-a-date', EMITTED_MS)).toBe(null);
});

test('notificationAgeMs: positive age measured against a server timestamp', () => {
    expect(notificationAgeMs(serverTime(), EMITTED_MS)).toBe(0);
    expect(notificationAgeMs(serverTime(), EMITTED_MS + 5000)).toBe(5000);
});

// ----------------------------------------------------------
// shouldShowNotification
// ----------------------------------------------------------

test('shouldShowNotification: false without a payload or session id', () => {
    expect(shouldShowNotification(null, ctx())).toBe(false);
    expect(shouldShowNotification({}, ctx())).toBe(false);
    expect(shouldShowNotification({ session_id: 0 }, ctx())).toBe(false);
});

test('shouldShowNotification: a visible, inactive, fresh notification shows', () => {
    expect(shouldShowNotification(payload(), ctx())).toBe(true);
});

test('shouldShowNotification: the session open and active here is suppressed', () => {
    expect(shouldShowNotification(payload(), ctx({ isActive: true }))).toBe(false);
});

test('shouldShowNotification: a hidden or background tab never toasts', () => {
    expect(shouldShowNotification(payload(), ctx({ isVisible: false }))).toBe(false);
});

test('shouldShowNotification: a stale replayed notification is dropped', () => {
    const stale = ctx({ now: EMITTED_MS + NOTIFICATION_FRESHNESS_MS + 1 });
    expect(shouldShowNotification(payload(), stale)).toBe(false);
    const fresh = ctx({ now: EMITTED_MS + NOTIFICATION_FRESHNESS_MS - 1 });
    expect(shouldShowNotification(payload(), fresh)).toBe(true);
});

test('shouldShowNotification: a missing or unparsable timestamp counts as fresh', () => {
    expect(shouldShowNotification(payload({ at: undefined }), ctx())).toBe(true);
    expect(shouldShowNotification(payload({ at: 'nope' }), ctx())).toBe(true);
});

test('shouldShowNotification: the freshness window is configurable', () => {
    const c = ctx({ now: EMITTED_MS + 5000, freshnessMs: 1000 });
    expect(shouldShowNotification(payload(), c)).toBe(false);
    expect(shouldShowNotification(payload(), { ...c, freshnessMs: 10000 })).toBe(true);
});
