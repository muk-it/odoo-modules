import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { queryFirst } from '@odoo/hoot-dom';
import { freezeTime, mockDate } from '@odoo/hoot-mock';
import { Component, xml } from '@odoo/owl';
import {
    mountWithCleanup,
    patchTranslations,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { localization } from '@web/core/l10n/localization';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import { formatTimestamp } from '@muk_ai/chat/utils';
import '@muk_ai_schedule/chat/tools/tool_card';

describe.current.tags('muk_ai_schedule');
defineMailModels();

beforeEach(() => {
    patchTranslations();
    patchWithCleanup(localization, {
        dateFormat: 'MM/dd/yyyy',
        timeFormat: 'HH:mm:ss',
        dateTimeFormat: 'MM/dd/yyyy HH:mm:ss',
    });
});

const RESUME_AT = '2026-07-01 12:05:12';

class Parent extends Component {
    static components = { ToolCard };
    static props = { block: { type: Object } };
    static template = xml`<ToolCard block="props.block"/>`;
}

/**
 * Fold one tool call and its result into a decorated tool block.
 * @param {string} name the schedule tool name
 * @param {object|string} args the call arguments, parsed or raw JSON
 * @param {*} result the tool result, or null while still running
 * @returns {object} the decorated block
 */
function scheduleBlock(name, args, result = null) {
    const log = [{ kind: 'tool_call', name, arguments: args, call_id: 'c1' }];
    if (result !== null) {
        log.push({ kind: 'tool_result', call_id: 'c1', result });
    }
    return buildRenderedTurns(log)[0].blocks[0];
}

/**
 * Pin the clock so the relative part of the band is deterministic.
 * @returns {string} the absolute text the band shows for ``RESUME_AT``
 */
function freezeClock() {
    mockDate('2026-07-01T12:00:00.000Z');
    freezeTime();
    return formatTimestamp(RESUME_AT);
}

test('schedule_resume block gets kind, clock icon and the paused band', async () => {
    const absolute = freezeClock();
    const block = scheduleBlock(
        'schedule_resume',
        { prompt: 'Check the inbox' },
        { ok: true, resume_at: RESUME_AT },
    );
    expect(block.kind).toBe('schedule_resume');
    expect(block.icon).toBe('fa-clock-o');
    expect(block.band).toBe(
        `Paused — resumes ${absolute} (5m 12s) · Will ask: "Check the inbox"`,
    );
    await mountWithCleanup(Parent, { props: { block } });
    expect('.mk_tool_schedule_resume').toHaveCount(1);
    expect('.mk_tool_icon .fa-clock-o').toHaveCount(1);
    expect('.mk_tool_band.text-danger').toHaveCount(0);
    expect(queryFirst('.mk_tool_band').textContent).toBe(block.band);
});

test('schedule_recur block gets kind, refresh icon and the recurring band', async () => {
    const absolute = freezeClock();
    const block = scheduleBlock(
        'schedule_recur',
        { every: 300, max_runs: 3, prompt: 'Poll the queue' },
        '{"ok": true, "resume_at": "2026-07-01 12:05:12", "runs_done": 1}',
    );
    expect(block.kind).toBe('schedule_recur');
    expect(block.icon).toBe('fa-refresh');
    expect(block.band).toBe(
        `Every 5m · run 1/3 · next ${absolute} (5m 12s) · Each fire asks: "Poll the queue"`,
    );
    await mountWithCleanup(Parent, { props: { block } });
    expect('.mk_tool_schedule_recur').toHaveCount(1);
    expect('.mk_tool_icon .fa-refresh').toHaveCount(1);
    expect(queryFirst('.mk_tool_band').textContent).toBe(block.band);
});

test('unbounded recurrence shows an infinity run cap before any result', () => {
    const block = scheduleBlock('schedule_recur', '{"every": 3600}');
    expect(block.band).toBe('Every 1h · run 0/∞');
});

test('band reflects the result that lands after decoration', () => {
    freezeClock();
    const block = scheduleBlock('schedule_resume', { prompt: 'Later' });
    expect(block.band).toBe('Paused — resumes  · Will ask: "Later"');
    block.result = { ok: true, resume_at: RESUME_AT };
    expect(block.band).toMatch(/^Paused — resumes .+ \(5m 12s\) · Will ask: "Later"$/);
});

test('failed schedule call keeps its kind but shows the warning icon and red band', async () => {
    const block = scheduleBlock(
        'schedule_resume',
        { prompt: 'x' },
        { ok: false, error: 'cap exceeded', cap: 'max_runs' },
    );
    expect(block.kind).toBe('schedule_resume');
    expect(block.icon).toBe('fa-exclamation-triangle');
    expect(block.band).toBe('cap exceeded: max_runs');
    await mountWithCleanup(Parent, { props: { block } });
    expect('.mk_tool_schedule_resume').toHaveCount(1);
    expect('.mk_tool_error').toHaveCount(0);
    expect('.mk_tool_icon .fa-exclamation-triangle').toHaveCount(1);
    expect(queryFirst('.mk_tool_band.text-danger').textContent).toBe(
        'cap exceeded: max_runs',
    );
});

test('prompt preview is cut at 200 characters', () => {
    const block = scheduleBlock('schedule_resume', { prompt: 'p'.repeat(250) });
    expect(block.band.endsWith('p'.repeat(200) + '…"')).toBe(true);
});

test('other tools are left untouched', () => {
    const block = scheduleBlock('search_read', { model: 'res.partner' }, { ok: true });
    expect(block.kind).toBe(undefined);
    expect(block.icon).toBe(undefined);
    expect(block.band).toBe(undefined);
});
