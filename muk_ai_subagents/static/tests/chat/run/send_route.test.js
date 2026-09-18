import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { patchTranslations } from '@web/../tests/web_test_helpers';

import { sessionSendRoutes } from '@muk_ai/chat/session/use_ai_session';

import {
    subagentPlaceholder,
    waitingSeconds,
} from '@muk_ai_subagents/chat/run/run_store';

describe.current.tags('muk_ai_subagents');

beforeEach(() => {
    patchTranslations();
});

const PARENT_ID = 7;

const WORKING = { id: 12, name: 'Bob: read', agent_name: 'Bob', state: 'running' };
const REPORTED = { id: 12, name: 'Bob: read', agent_name: 'Bob', state: 'done' };
const ASKING = {
    ...WORKING,
    state: 'waiting',
    waiting: { kind: 'question', text: 'Which quarter?' },
};
const APPROVING = {
    ...WORKING,
    state: 'waiting',
    waiting: { kind: 'approval', text: 'Write the record?' },
};

/** Return the one send route this addon registers. */
function route() {
    return sessionSendRoutes.get('muk_ai_subagents.steer');
}

/** Build the session state a composer sends from, recording every call. */
function context(open, children) {
    const calls = [];
    const state = {
        sessionId: PARENT_ID,
        subagentOpen: open,
        subagentRun: children ? { children } : null,
    };
    const orm = {
        async call(model, method, args) {
            calls.push({ method, args });
            return { children: children || [] };
        },
    };
    return { state, orm, calls };
}

test('with no subagent open the composer writes to the conversation', async () => {
    const { state, orm, calls } = context(null, null);
    expect(await route()({ state, orm }, 'hello')).toBe(false);
    expect(calls).toHaveLength(0);
});

test('an empty message is swallowed rather than sent to a subagent', async () => {
    const { state, orm, calls } = context(WORKING, [WORKING]);
    expect(await route()({ state, orm }, '   ')).toBe(true);
    expect(calls).toHaveLength(0);
});

test('a subagent blocked on a question is answered, not steered', async () => {
    // Steering would queue the text for a turn that cannot start until the
    // question is answered, and the person who just typed it would wait.
    const { state, orm, calls } = context(ASKING, [ASKING]);
    expect(await route()({ state, orm }, 'Q2')).toBe(true);
    expect(calls).toEqual([{ method: 'answer', args: [ASKING.id, 'Q2'] }]);
});

test('a subagent blocked on an approval is steered, not answered', async () => {
    const { state, orm, calls } = context(APPROVING, [APPROVING]);
    await route()({ state, orm }, 'stop that');
    expect(calls[0].method).toBe('subagent_steer');
    expect(calls[0].args).toEqual([PARENT_ID, APPROVING.id, 'stop that']);
});

test('a working subagent takes direction and the roster comes back', async () => {
    const { state, orm, calls } = context(WORKING, [WORKING]);
    await route()({ state, orm }, 'Only Q2.');
    expect(calls[0].method).toBe('subagent_steer');
    expect(state.subagentRun.children).toEqual([WORKING]);
    expect(state.subagentRun.receivedAt).not.toBe(undefined);
});

test('the placeholder promises only what the server will accept', () => {
    expect(subagentPlaceholder({ state: { subagentOpen: null } })).toBe('');
    // parked on its subagents: there is no question to answer, the text queues
    expect(
        String(
            subagentPlaceholder({
                state: { subagentOpen: null, pendingAsk: { kind: 'children' } },
            }),
        ),
    ).toInclude('will queue');
    expect(
        String(
            subagentPlaceholder({
                state: { subagentOpen: WORKING, subagentRun: { children: [WORKING] } },
            }),
        ),
    ).toInclude('current step');
    // reported, but a sibling is still working: the server refuses
    const live = [REPORTED, { id: 13, name: 'Cy', state: 'running' }];
    expect(
        String(
            subagentPlaceholder({
                state: { subagentOpen: REPORTED, subagentRun: { children: live } },
            }),
        ),
    ).toInclude('once the run has ended');
    expect(
        String(
            subagentPlaceholder({
                state: {
                    subagentOpen: REPORTED,
                    subagentRun: { children: [REPORTED] },
                },
            }),
        ),
    ).toInclude('for more');
});

test('waiting time counts only from a question that was actually asked', () => {
    expect(waitingSeconds(WORKING)).toBe(0);
    expect(waitingSeconds({ ...ASKING, waiting_since: null })).toBe(0);
    expect(
        waitingSeconds({ ...ASKING, waiting_since: '2000-01-01 00:00:00' }),
    ).toBeGreaterThan(0);
});
