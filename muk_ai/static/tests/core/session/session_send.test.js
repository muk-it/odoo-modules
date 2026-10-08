import { expect, test } from '@odoo/hoot';
import { onRpc } from '@web/../tests/web_test_helpers';

import { sessionSendRoutes, slashCommands } from '@muk_ai/core/session/session';
import {
    defineAIModels,
    openSession,
    pngFile,
    recordNotifications,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const history = [{ kind: 'user_message', content: 'before', event_id: 1, sequence: 1 }];

test('a message goes to the method the state of the chat calls for', async () => {
    const cases = [
        [{ events: [] }, 'start', 'user_message'],
        [{ events: history, iteration_count: 1 }, 'send_message', 'user_message'],
        [
            {
                state: 'waiting',
                pending_ask: { kind: 'question', text: 'Which?', call_id: 'c1' },
            },
            'answer',
            'answer',
        ],
    ];
    for (const [values, method, kind] of cases) {
        onRpc('muk_ai.session', 'get_snapshot', () => snapshot(values));
        onRpc('muk_ai.session', method, ({ args, kwargs }) => {
            expect.step(`${method} ${args[1]} ${kwargs.attachment_ids}`);
            return snapshot({ ...values, state: 'running' });
        });
        const session = await openSession(1);
        session.state.input = 'Go';
        await session.send();
        expect.verifySteps([`${method} Go `]);
        expect(session.state.events.at(-1).kind).toBe(kind);
        expect(session.state.input).toBe('');
        session.chat.release(1);
        session.chat.sessions.delete(1);
    }
});

test('a message typed while a turn runs is queued and shown at once', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ state: 'running', events: history }),
    );
    onRpc('muk_ai.session', 'enqueue_message', ({ args }) => {
        expect.step(`enqueue ${args[1]}`);
        return snapshot({
            state: 'running',
            events: history,
            pending_user_messages: [
                { content: args[1], queued_at: '2026-01-01 10:00:00' },
            ],
        });
    });
    const session = await openSession(1);
    session.state.input = 'Later';
    const sending = session.send();
    expect(session.data.pending_user_messages.map((item) => item.content)).toEqual([
        'Later',
    ]);
    await sending;
    expect.verifySteps(['enqueue Later']);
    expect(session.data.pending_user_messages[0].queued_at).toBe('2026-01-01 10:00:00');
});

test('a message the queue refused because the turn ended is sent again, keeping the draft', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ state: 'running', events: history }),
    );
    onRpc('muk_ai.session', 'enqueue_message', () =>
        snapshot({
            state: 'done',
            events: history,
            iteration_count: 1,
            queue_rejected_state: 'done',
        }),
    );
    onRpc('muk_ai.session', 'send_message', ({ args }) => {
        expect.step(`send ${args[1]}`);
        return snapshot({ state: 'running', events: history });
    });
    const session = await openSession(1);
    session.state.input = 'Queued';
    const sending = session.send();
    session.state.input = 'Draft';
    await sending;
    expect.verifySteps(['send Queued']);
    expect(session.state.input).toBe('Draft');
});

test('a failed message marks the chat in error, a failed answer restores the question', async () => {
    const ask = { kind: 'question', text: 'Which?', call_id: 'c1' };
    for (const [values, method, state] of [
        [{ events: history, iteration_count: 1 }, 'send_message', 'error'],
        [{ state: 'waiting', pending_ask: ask }, 'answer', 'waiting'],
    ]) {
        onRpc('muk_ai.session', 'get_snapshot', () => snapshot(values));
        onRpc('muk_ai.session', method, () => {
            throw new Error('provider down');
        });
        const session = await openSession(1);
        session.state.input = 'Go';
        await session.send();
        expect(session.data.state).toBe(state);
        expect(session.data.error_message).toInclude('provider down');
        session.chat.release(1);
        session.chat.sessions.delete(1);
    }
});

test('slash commands run instead of being sent, unknown ones are sent as text', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({
            events: history,
            iteration_count: 1,
            view_context: { kind: 'list', model: 'res.partner' },
        }),
    );
    onRpc('muk_ai.session', '*', ({ method, args }) => {
        if (
            [
                'clear',
                'compact',
                'unpin_view_context',
                'send_message',
                'write',
            ].includes(method)
        ) {
            expect.step(
                method === 'write' ? `write ${JSON.stringify(args[1])}` : method,
            );
            return method === 'write'
                ? true
                : snapshot({
                      events: history,
                      iteration_count: 1,
                      view_context: { kind: 'list', model: 'res.partner' },
                  });
        }
    });
    const session = await openSession(1);
    for (const [text, step] of [
        ['/clear', 'clear'],
        ['/Compact', 'compact'],
        ['/unpin', 'unpin_view_context'],
        ['/agent anal', 'write {"agent_id":2}'],
        ['/nothing here', 'send_message'],
    ]) {
        session.state.input = text;
        await session.send();
        expect.verifySteps([step]);
    }
    session.state.input = '/help';
    await session.send();
    const help = session.state.events.at(-1);
    expect(help.kind).toBe('command');
    expect(help.summary).toInclude('**/handover**');
});

test('an addon slash command and a send route take the message first', async () => {
    slashCommands.add('/remember', {
        hint: 'Remember',
        run: (session, args) => session.appendCommand('/remember', { summary: args }),
    });
    sessionSendRoutes.add(
        'voice',
        async (session, text) => text === 'voice' && expect.step('route'),
    );
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ events: history }));
    const session = await openSession(1);
    session.state.input = '/remember the milk';
    await session.send();
    expect(session.state.events.at(-1).summary).toBe('the milk');
    session.state.input = 'voice';
    await session.send();
    expect.verifySteps(['route']);
    expect(session.state.input).toBe('');
});

test('files are uploaded to be sent with the next message and can be dropped again', async () => {
    onRpc('muk_ai.session', 'upload_attachments', ({ args }) => {
        expect.step(`upload ${args[1][0].filename} ${args[1][0].mimetype}`);
        return [{ id: 31, filename: 'shot.png', mimetype: 'image/png' }];
    });
    onRpc('muk_ai.session', 'discard_attachments', ({ args }) =>
        expect.step(`discard ${args[1]}`),
    );
    const session = await openSession(1);
    await session.attach([pngFile()]);
    expect(session.state.attachments.map((file) => file.id)).toEqual([31]);
    expect(session.canSend).toBe(true);
    await session.detach(31);
    expect(session.state.attachments).toEqual([]);
    expect.verifySteps(['upload shot.png image/png', 'discard 31']);
});

test('a filling context window warns once and an overflowing one compacts first', async () => {
    const notes = await recordNotifications();
    onRpc('muk_ai.session', 'compact', () => {
        expect.step('compact');
        return snapshot();
    });
    for (const [tokens, steps, note] of [
        [5600, [], 'Context window at 70%'],
        [5700, [], null],
        [7000, ['compact'], 'Auto-compacted'],
    ]) {
        onRpc('muk_ai.session', 'get_snapshot', () =>
            snapshot({
                events: history,
                iteration_count: 1,
                last_input_tokens: tokens,
            }),
        );
        const session = await openSession(1);
        session.state.compactWarned = tokens === 5700;
        notes.length = 0;
        await session.autoCompact();
        expect.verifySteps(steps);
        expect(notes.map((item) => item.message.slice(0, note?.length))).toEqual(
            note ? [note] : [],
        );
        session.chat.release(1);
        session.chat.sessions.delete(1);
    }
});
