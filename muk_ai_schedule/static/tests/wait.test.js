import { describe, expect, test } from '@odoo/hoot';
import { click, queryAllTexts } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, xml } from '@odoo/owl';
import { mockService, mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';

describe.current.tags('muk_ai_schedule');
defineMailModels();

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

class Composer extends Component {
    static components = { ChatComposer };
    static props = { session: { type: Object } };
    static template = xml`
        <ChatComposer
            session="props.session"
            value="''"
            placeholder="'Message'"
            onInput="() => {}"
            onSend="() => {}"
        />
    `;
}

class Card extends Component {
    static components = { ToolCard };
    static props = { block: { type: Object } };
    static template = xml`<ToolCard block="props.block"/>`;
}

/**
 * Show the composer of a chat and record the actions asked of it.
 * @param {object} pendingAsk what the chat waits for
 * @param {boolean} writable whether the viewer may act on the chat
 */
async function mountComposer(pendingAsk, writable = true) {
    mockService('orm', {
        call: async (model, method) => {
            expect.step(method);
            return {};
        },
    });
    const session = {
        state: { status: 'waiting', pendingAsk, sessionId: 1 },
        canWrite: () => writable,
        applySnapshot: () => expect.step('applySnapshot'),
        onStop: () => expect.step('onStop'),
    };
    await mountWithCleanup(Composer, { props: { session } });
}

test('a waiting chat says what it waits for and is woken or stopped from the bar', async () => {
    await mountComposer(PLAN);
    expect('.mk_wait_bar_note').toHaveText('Remind the customer');
    expect('.mk_wait_bar_line').toHaveText(/^Waiting until /);
    expect('.mk_composer_host textarea').toHaveAttribute(
        'placeholder',
        'Waiting. Type to wake the agent...',
    );
    await click('.mk_wait_bar_wake');
    await animationFrame();
    await click('.mk_wait_bar_stop');
    expect.verifySteps(['action_wake_now', 'applySnapshot', 'onStop']);
});

test('the bar names the record and what it waits for on it', async () => {
    for (const watch of [
        { condition: [['email', '!=', false]] },
        { on_message: true },
        { condition: [['email', '!=', false]], on_message: true },
    ]) {
        await mountComposer({ ...PLAN, record: RECORD, ...watch });
    }
    const lines = queryAllTexts('.mk_wait_bar_line');
    expect(lines.map((line) => line.replace(/, until .*/, ''))).toEqual([
        'Waiting for Acme to be ready',
        'Waiting for a message on Acme',
        'Waiting for Acme to be ready or for a message',
    ]);
});

test('a reader sees what the chat waits for without the buttons', async () => {
    await mountComposer(PLAN, false);
    expect('.mk_wait_bar').toHaveCount(1);
    expect('.mk_wait_bar button').toHaveCount(0);
});

test('a chat waiting for an approval shows no wait bar', async () => {
    await mountComposer({ kind: 'approval' });
    expect('.mk_wait_bar').toHaveCount(0);
    expect('.mk_composer_host textarea').toHaveAttribute('placeholder', 'Message');
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
        [{ status: 'cancelled', reason: 'stopped_by_user' }, 'Stopped while waiting'],
        [{ status: 'condition_met' }, 'The record was ready already'],
    ];
    for (const [result] of results) {
        const [turn] = buildRenderedTurns([
            {
                kind: 'tool_call',
                call_id: 'w1',
                name: 'wait',
                arguments: { note: 'n', model: 'res.partner', record_id: 7 },
            },
            { kind: 'tool_result', call_id: 'w1', result },
        ]);
        await mountWithCleanup(Card, { props: { block: turn.blocks[0] } });
    }
    expect(new Set(queryAllTexts('.mk_tool_name'))).toEqual(
        new Set(['Wait for res.partner']),
    );
    expect(queryAllTexts('.mk_tool_band')).toEqual(results.map(([, text]) => text));
});
