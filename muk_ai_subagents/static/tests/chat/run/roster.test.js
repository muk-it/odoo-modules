import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { patchTranslations } from '@web/../tests/web_test_helpers';

import { sessionEventHandlers } from '@muk_ai/chat/session/use_ai_session';

import { groupRoster } from '@muk_ai_subagents/chat/run/roster';
import {
    childAsk,
    formatElapsed,
    isCleanStop,
    isFailed,
} from '@muk_ai_subagents/chat/run/run_store';

describe.current.tags('muk_ai_subagents');

beforeEach(() => {
    patchTranslations();
});

const BLOCKED = {
    id: 1,
    name: 'Ada',
    state: 'waiting',
    waiting: { kind: 'approval', text: 'Write the record?' },
};
const WORKING = { id: 2, name: 'Bob', state: 'running', waiting: null };
const DONE = { id: 3, name: 'Cy', state: 'done', stop_reason: 'done' };
const DONE_TOO = { id: 4, name: 'Di', state: 'done', stop_reason: '' };
const FAILED = { id: 5, name: 'Ed', state: 'stopped', stop_reason: 'cost_limit' };
const ERRORED = { id: 6, name: 'Flo', state: 'error', stop_reason: 'done' };

test('rows are grouped by urgency: needs you, stopped early, working, done', () => {
    const groups = groupRoster([DONE, WORKING, BLOCKED, FAILED]);
    expect(groups.needsYou.map((c) => c.id)).toEqual([1]);
    expect(groups.failed.map((c) => c.id)).toEqual([5]);
    expect(groups.working.map((c) => c.id)).toEqual([2]);
    expect(groups.done.map((c) => c.id)).toEqual([3]);
    expect(groups.collapsed).toEqual([]);
});

test('finished rows stay listed while anything still runs', () => {
    const groups = groupRoster([DONE, DONE_TOO, FAILED, WORKING]);
    expect(groups.done.map((c) => c.id)).toEqual([3, 4]);
    expect(groups.failed.map((c) => c.id)).toEqual([5]);
    expect(groups.collapsed).toEqual([]);
});

test('finished rows collapse once the run is idle, and a failure never does', () => {
    const groups = groupRoster([DONE, DONE_TOO, FAILED, ERRORED], { openId: 4 });
    expect(groups.needsYou).toEqual([]);
    expect(groups.working).toEqual([]);
    expect(groups.failed.map((c) => c.id)).toEqual([5, 6]);
    expect(groups.done.map((c) => c.id)).toEqual([4]);
    expect(groups.collapsed.map((c) => c.id)).toEqual([3]);
});

test('a blocked child never collapses, whatever its state says', () => {
    const blockedDone = { ...DONE, waiting: { kind: 'question', text: 'Which?' } };
    const groups = groupRoster([blockedDone, DONE_TOO]);
    expect(groups.needsYou.map((c) => c.id)).toEqual([3]);
    expect(groups.collapsed).toEqual([]);
});

test('childAsk reads the ask the roster sends, or nothing', () => {
    expect(childAsk(BLOCKED).kind).toBe('approval');
    expect(childAsk(WORKING)).toBe(null);
    expect(childAsk(null)).toBe(null);
});

test('isCleanStop and isFailed agree on what went wrong', () => {
    expect(isCleanStop('')).toBe(true);
    expect(isCleanStop('cost_limit')).toBe(false);
    expect(isFailed(DONE)).toBe(false);
    expect(isFailed(FAILED)).toBe(true);
    expect(isFailed(ERRORED)).toBe(true);
    expect(isFailed({ ...WORKING, stop_reason: 'cost_limit' })).toBe(false);
});

test('formatElapsed picks the unit for the size of the duration', () => {
    expect(formatElapsed(0)).toBe('');
    expect(formatElapsed(12)).toBe('12s');
    expect(formatElapsed(245)).toBe('4m 05s');
    expect(formatElapsed(3780)).toBe('1h 03m');
});

test('the subagent_update handler stamps the roster onto the session state', () => {
    const handle = sessionEventHandlers.get('subagent_update');
    const state = { subagentRun: null };
    handle({ children: [WORKING], total_cost: 0.5, cost_limit: 2 }, { state });
    expect(state.subagentRun.children).toEqual([WORKING]);
    expect(state.subagentRun.total_cost).toBe(0.5);
    expect(typeof state.subagentRun.receivedAt).toBe('number');
    handle({}, { state });
    expect(state.subagentRun.children).toEqual([]);
});
