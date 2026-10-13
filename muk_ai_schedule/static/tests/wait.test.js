import { describe, expect, queryAllTexts, queryOne, test } from '@odoo/hoot';
import { contains, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import {
    defineAIModels,
    emitEvent,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();
describe.current.tags('muk_ai_schedule');

const RECORD = { model: 'res.partner', id: 7, name: 'Acme' };

const PLAN = {
    kind: 'wakeup',
    call_id: 'w1',
    resume_at: '2030-01-01 09:00:00',
    note: 'Remind the customer',
    record: false,
    condition: false,
    on_message: false,
};

const waitCall = (callId, args) => ({
    kind: 'tool_call',
    call_id: callId,
    name: 'wait',
    arguments: JSON.stringify(args),
});

/**
 * Show a chat and record the actions asked of it.
 * @param {object} values the snapshot values of the chat
 */
async function mountChat(values) {
    const chat = snapshot(values);
    onRpc('muk_ai.session', 'get_snapshot', () => chat);
    for (const method of ['action_wake_now', 'action_stop']) {
        onRpc('muk_ai.session', method, () => {
            expect.step(method);
            return chat;
        });
    }
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session } });
}

test('a waiting chat says what it waits for and is woken or stopped from the bar', async () => {
    await mountChat({
        state: 'waiting',
        pending_ask: PLAN,
        events: [waitCall('w1', { note: PLAN.note, seconds: 3600 })],
    });
    expect('.mk_tool').toHaveCount(0);
    expect('.mk_wait_bar_note').toHaveText('Remind the customer');
    expect('.mk_wait_bar_line').toHaveText(/^Waiting until /);
    expect('.mk_composer textarea').toHaveAttribute(
        'placeholder',
        'Waiting. Type to wake the agent...',
    );
    const lines = [];
    for (const watch of [
        { condition: [['email', '!=', false]] },
        { on_message: true },
        { condition: [['email', '!=', false]], on_message: true },
    ]) {
        await emitEvent(1, 'state', {
            state: 'waiting',
            ask: { ...PLAN, record: RECORD, ...watch },
        });
        lines.push(queryOne('.mk_wait_bar_line').textContent.replace(/, until .*/, ''));
    }
    expect(lines).toEqual([
        'Waiting for Acme to be ready',
        'Waiting for a message on Acme',
        'Waiting for Acme to be ready or for a message',
    ]);
    await contains('.mk_wait_bar_wake').click();
    await contains('.mk_wait_bar_stop').click();
    expect.verifySteps(['action_wake_now', 'action_stop']);
    await emitEvent(1, 'state', { state: 'running' });
    expect('.mk_wait_bar').toHaveCount(0);
});

test('a reader sees what the chat waits for without the buttons', async () => {
    await mountChat({ state: 'waiting', pending_ask: PLAN, can_write: false });
    expect('.mk_wait_bar').toHaveCount(1);
    expect('.mk_wait_bar button').toHaveCount(0);
});

test('a finished wait tells why the chat woke up', async () => {
    const results = [
        [{ status: 'woken', reason: 'time' }, 'Woke up on time'],
        [{ status: 'woken', reason: 'timeout' }, 'Woke up: the wait timed out'],
        [{ status: 'woken', reason: 'condition_met' }, 'Woke up: the record is ready'],
        [
            { status: 'woken', reason: 'message', message: { author: 'Ann' } },
            'Woke up: Ann wrote a message',
        ],
        [{ status: 'woken', reason: 'record_deleted' }, 'Woke up: the record is gone'],
        [
            { status: 'woken', reason: 'condition_invalid' },
            'Woke up: the condition no longer works',
        ],
        [{ status: 'woken', reason: 'manual' }, 'Woken up by hand'],
        [{ status: 'woken', reason: 'user_message' }, 'Woken up by a message'],
        [{ error: 'interrupted', reason: 'stopped_by_user' }, 'Stopped while waiting'],
        [{ status: 'condition_met' }, 'The record was ready already'],
    ];
    await mountChat({
        events: results.flatMap(([result], index) => [
            waitCall(`w${index}`, { note: 'n', model: 'res.partner', record_id: 7 }),
            {
                kind: 'tool_result',
                call_id: `w${index}`,
                result: JSON.stringify(result),
            },
            { kind: 'text', content: `step ${index}` },
        ]),
    });
    expect(queryAllTexts('.mk_tool_name')[0]).toBe('Wait for Partner');
    expect(queryAllTexts('.mk_tool_band')).toEqual(results.map(([, text]) => text));
});
