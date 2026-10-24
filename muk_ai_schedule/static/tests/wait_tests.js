// @odoo-module

import { reactive } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { click, getFixture, mount, nextTick } from '@web/../tests/helpers/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import { WaitBar } from '@muk_ai_schedule/chat/wait_bar/wait_bar';
import '@muk_ai_schedule/chat/composer/composer';
import '@muk_ai_schedule/chat/wait_card/wait_card';

QUnit.module('wait');

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

/**
 * Build a chat waiting on ``pendingAsk`` that records what is asked of it.
 * @param {object} pendingAsk what the chat waits for
 * @param {Array} steps collects the actions asked of the chat
 * @param {boolean} writable whether the viewer may act on the chat
 * @returns {object} the session
 */
function waitingSession(pendingAsk, steps, writable = true) {
    return {
        state: reactive({ status: 'waiting', pendingAsk, sessionId: 1 }),
        canWrite: () => writable,
        applySnapshot: () => steps.push('applySnapshot'),
        onStop: () => steps.push('onStop'),
    };
}

/**
 * Mount the wait bar of a chat.
 * @param {object} session the chat
 * @param {Array} steps collects the server calls
 * @returns {Promise<HTMLElement>} the fixture
 */
async function mountBar(session, steps) {
    registry
        .category('services')
        .add('notification', { start: () => ({ add: () => {} }) }, { force: true });
    const env = await makeTestEnv({
        mockRPC: (route, { method }) => {
            steps.push(method);
            return {};
        },
    });
    const target = getFixture();
    await mount(WaitBar, target, { env, props: { session } });
    return target;
}

QUnit.test(
    'a waiting chat says what it waits for and is woken or stopped from the bar',
    async (assert) => {
        const steps = [];
        const session = waitingSession(PLAN, steps);
        const target = await mountBar(session, steps);
        assert.strictEqual(
            target.querySelector('.mk_wait_bar_note').textContent,
            'Remind the customer',
        );
        assert.ok(
            target
                .querySelector('.mk_wait_bar_line')
                .textContent.startsWith('Waiting until '),
        );
        await click(target, '.mk_wait_bar_wake');
        await nextTick();
        await click(target, '.mk_wait_bar_stop');
        assert.deepEqual(steps, ['action_wake_now', 'applySnapshot', 'onStop']);
        session.state.status = 'running';
        await nextTick();
        assert.containsNone(target, '.mk_wait_bar');
    },
);

QUnit.test('the bar names the record and what it waits for on it', async (assert) => {
    const lines = [];
    for (const watch of [
        { condition: [['email', '!=', false]] },
        { on_message: true },
        { condition: [['email', '!=', false]], on_message: true },
    ]) {
        const target = await mountBar(
            waitingSession({ ...PLAN, record: RECORD, ...watch }, []),
            [],
        );
        const bars = target.querySelectorAll('.mk_wait_bar_line');
        lines.push(bars[bars.length - 1].textContent.replace(/, until .*/, ''));
    }
    assert.deepEqual(lines, [
        'Waiting for Acme to be ready',
        'Waiting for a message on Acme',
        'Waiting for Acme to be ready or for a message',
    ]);
});

QUnit.test(
    'a reader sees what the chat waits for without the buttons',
    async (assert) => {
        const target = await mountBar(waitingSession(PLAN, [], false), []);
        assert.containsOnce(target, '.mk_wait_bar');
        assert.containsNone(target, '.mk_wait_bar button');
    },
);

QUnit.test('the composer of a waiting chat says typing wakes the agent', (assert) => {
    const { get } = Object.getOwnPropertyDescriptor(
        ChatComposer.prototype,
        'composerPlaceholder',
    );
    const placeholder = (session) =>
        get.call({ props: { session, placeholder: 'Message' } });
    assert.strictEqual(
        String(placeholder(waitingSession(PLAN, []))),
        'Waiting. Type to wake the agent...',
    );
    assert.strictEqual(
        placeholder(waitingSession({ kind: 'approval' }, [])),
        'Message',
    );
    assert.strictEqual(placeholder(undefined), 'Message');
});

QUnit.test('a finished wait tells why the chat woke up', (assert) => {
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
        [{ status: 'cancelled', reason: 'stopped_by_user' }, 'Stopped while waiting'],
        [{ status: 'condition_met' }, 'The record was ready already'],
    ];
    const blocks = results.map(([result]) => {
        const [turn] = buildRenderedTurns([
            {
                kind: 'tool_call',
                call_id: 'w1',
                name: 'wait',
                arguments: { note: 'n', model: 'res.partner', record_id: 7 },
            },
            { kind: 'tool_result', call_id: 'w1', result },
        ]);
        return turn.blocks[0];
    });
    assert.deepEqual(
        blocks.map((block) => String(block.band)),
        results.map(([, text]) => text),
    );
    assert.strictEqual(String(blocks[0].label), 'Wait for res.partner');
    assert.strictEqual(blocks[0].icon, 'fa-clock-o');
});
