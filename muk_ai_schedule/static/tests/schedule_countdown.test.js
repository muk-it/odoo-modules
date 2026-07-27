import { advanceTime, describe, expect, test } from '@odoo/hoot';
import { animationFrame, queryAllTexts, queryText } from '@odoo/hoot-dom';
import { mockDate } from '@odoo/hoot-mock';
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    mountWithCleanup,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ScheduleCountdownField } from '@muk_ai_schedule/views/fields/schedule_countdown/schedule_countdown';

describe.current.tags('muk_ai_schedule');
defineMailModels();

const { DateTime } = luxon;

const NOW = '2026-03-01 12:00:00';

const ARCH = `
    <form>
        <field name="resume_at" widget="schedule_countdown"/>
    </form>`;

class MukAiSession extends models.Model {
    _name = 'muk_ai.session';
    resume_at = fields.Datetime();
    _records = [
        { id: 1, resume_at: false },
        { id: 2, resume_at: '2026-03-01 11:00:00' },
        { id: 3, resume_at: '2026-03-01 12:00:30' },
        { id: 4, resume_at: '2026-03-01 12:05:30' },
    ];
}
defineModels([MukAiSession]);

/**
 * Install an inert bus mock so the widget can subscribe without a real bus.
 */
function mockBus() {
    mockService('bus_service', {
        subscribe() {},
        unsubscribe() {},
        addChannel() {},
        deleteChannel() {},
    });
}

/**
 * Pin the clock at the fixture time and render the widget for one record.
 *
 * The zone is pinned along with the date: `mockDate` leaves the time zone
 * untouched when none is given, so the countdown would otherwise be measured
 * against whatever zone the runner happens to carry. Every expectation below
 * is plain UTC arithmetic against the fixture targets.
 * @param {number} resId the session record to open
 * @returns {Promise<object>} the mounted form view
 */
async function mountCountdown(resId) {
    mockDate(NOW, 0);
    mockBus();
    return mountView({
        resModel: 'muk_ai.session',
        resId,
        type: 'form',
        arch: ARCH,
    });
}

/**
 * Build the minimal record props the field reads.
 * @param {string} resModel the model the field is bound to
 * @param {string|false} isoUtc the UTC target time, or false for an empty value
 * @returns {object} the record stub
 */
function makeRecord(resModel, isoUtc) {
    return {
        resModel,
        resId: 42,
        data: {
            resume_at: isoUtc ? DateTime.fromISO(isoUtc, { zone: 'utc' }) : false,
        },
    };
}

/**
 * Mount the field on a record stub over a mocked bus.
 * @param {string} resModel the model the field is bound to
 * @param {string|false} isoUtc the UTC target time, or false for an empty value
 * @returns {Promise<object>} the mounted component
 */
async function mountBareField(resModel, isoUtc) {
    mockDate(NOW, 0);
    mockBus();
    const field = await mountWithCleanup(ScheduleCountdownField, {
        props: { name: 'resume_at', record: makeRecord(resModel, isoUtc) },
    });
    return { field };
}

test('an empty target renders the em dash', async () => {
    await mountCountdown(1);
    expect(queryText('.mk_schedule_countdown')).toBe('—');
});

test('a past target renders the absolute datetime and the due label', async () => {
    await mountCountdown(2);
    const [absolute, due] = queryAllTexts('.mk_schedule_countdown span');
    expect(absolute).toMatch(/2026/);
    expect(due).toBe('(due)');
});

test('the rendered countdown ticks down as the seconds elapse', async () => {
    await mountCountdown(4);
    expect(queryText('.mk_schedule_countdown')).toMatch(/^5m \d+s$/);
    await advanceTime(60 * 1000);
    await animationFrame();
    expect(queryText('.mk_schedule_countdown')).toMatch(/^4m \d+s$/);
});

test('the rendered countdown flips to the due label once the target passes', async () => {
    await mountCountdown(3);
    expect(queryText('.mk_schedule_countdown')).toMatch(/^\d+s$/);
    await advanceTime(31 * 1000);
    await animationFrame();
    expect('.mk_schedule_countdown_due').toHaveText('(due)');
});

test('countdownText renders seconds under a minute', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T12:00:30');
    mockDate(NOW);
    expect(field.countdownText).toBe('30s');
});

test('countdownText renders minutes and seconds under an hour', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T12:05:30');
    mockDate(NOW);
    expect(field.countdownText).toBe('5m 30s');
});

test('countdownText renders hours and minutes under a day', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T14:20:00');
    mockDate(NOW);
    expect(field.countdownText).toBe('2h 20m');
});

test('countdownText renders days and hours beyond a day', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-04T15:00:00');
    mockDate(NOW);
    expect(field.countdownText).toBe('3d 3h');
});

test('countdownText is empty for an empty target', async () => {
    const { field } = await mountBareField('muk_ai.session', false);
    expect(field.isEmpty).toBe(true);
    expect(field.countdownText).toBe('');
});

test('countdownText is empty for an elapsed target', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T11:00:00');
    mockDate(NOW);
    expect(field.isPast).toBe(true);
    expect(field.countdownText).toBe('');
});

test('a running state event for this session forces a re-tick', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T13:00:00');
    const before = field.state.tick;
    field.busHandler({
        session_id: field.props.record.resId,
        type: 'state',
        payload: { state: 'running' },
    });
    expect(field.state.tick).toBe(before + 1);
});

test('a foreign, non-state, or non-running event never re-ticks', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T13:00:00');
    const before = field.state.tick;
    field.busHandler({ session_id: 999, type: 'state', payload: { state: 'running' } });
    field.busHandler({
        session_id: field.props.record.resId,
        type: 'text',
        payload: { state: 'running' },
    });
    field.busHandler({
        session_id: field.props.record.resId,
        type: 'state',
        payload: { state: 'done' },
    });
    field.busHandler(null);
    field.busHandler({ session_id: field.props.record.resId, type: 'state' });
    expect(field.state.tick).toBe(before);
});

test('the field only listens to the bus on the session model', async () => {
    const { field } = await mountBareField('muk_ai.session', '2026-03-01T13:00:00');
    expect(typeof field.busHandler).toBe('function');
    const other = await mountBareField('res.partner', '2026-03-01T13:00:00');
    expect(other.field.busHandler).toBe(null);
});
