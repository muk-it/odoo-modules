import { expect, test } from '@odoo/hoot';
import { onRpc } from '@web/../tests/web_test_helpers';

import {
    defineAIModels,
    emitEvent,
    getChat,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const event = (sequence, values = {}) => ({
    kind: 'text',
    content: `event ${sequence}`,
    event_id: sequence,
    sequence,
    ...values,
});

test('a chat loads with one snapshot call holding its values and transcript', async () => {
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) => {
        expect.step(`get_snapshot ${args[0]}`);
        return snapshot({
            name: 'Quarterly',
            agent_id: [1, 'General'],
            events: [event(1), event(2)],
            has_more_older: true,
            oldest_sequence: 1,
        });
    });
    const session = await openSession(1);
    expect.verifySteps(['get_snapshot 1']);
    expect(session.data.name).toBe('Quarterly');
    expect(session.agentName).toBe('General');
    expect(session.readonly).toBe(false);
    expect(session.state.loading).toBe(false);
    expect(session.state.hasMoreOlder).toBe(true);
    expect(session.turns.map((turn) => turn.blocks[0].text)).toEqual([
        'event 1\n\nevent 2',
    ]);
});

test('a chat that cannot be read is flagged missing and stays read only', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => {
        throw new Error('gone');
    });
    const session = await openSession(4);
    expect(session.state.missing).toBe(true);
    expect(session.readonly).toBe(true);
});

test('a loading chat is not read only, cannot send, and replays bus events after the snapshot', async () => {
    const { promise, resolve } = Promise.withResolvers();
    onRpc('muk_ai.session', 'get_snapshot', () => promise);
    const chat = await getChat();
    const session = chat.acquire(1);
    expect(session.readonly).toBe(false);
    expect(session.canSend).toBe(false);
    await emitEvent(1, 'log', event(1));
    await emitEvent(1, 'log', event(2));
    expect(session.state.events).toEqual([]);
    resolve(snapshot({ events: [event(1)] }));
    await session.ready;
    expect(session.state.events.map((entry) => entry.event_id)).toEqual([1, 2]);
});

test('a snapshot window keeps the older events and the optimistic keys held', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ events: [event(5), event(6)] }),
    );
    const session = await openSession(1);
    session.state.events = [
        event(3),
        event(4),
        { kind: 'user_message', content: 'hi', _clientKey: 'ck1' },
    ];
    session.applySnapshot(
        snapshot({
            events: [event(5, { kind: 'user_message', content: 'hi' }), event(6)],
            oldest_sequence: 5,
        }),
    );
    expect(session.state.events.map((entry) => entry.sequence)).toEqual([3, 4, 5, 6]);
    expect(session.state.events[2]._clientKey).toBe('ck1');
});

test('loading older events prepends the page before the oldest one held', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ events: [event(10)], has_more_older: true, oldest_sequence: 10 }),
    );
    onRpc('muk_ai.session', 'fetch_events', ({ args, kwargs }) => {
        expect.step(`before ${kwargs.before_sequence}`);
        expect(args).toEqual([1]);
        return {
            events: [event(8), event(9), event(10)],
            oldest_sequence: 8,
            has_more_older: false,
        };
    });
    const session = await openSession(1);
    await session.loadMoreEvents();
    expect.verifySteps(['before 10']);
    expect(session.state.events.map((entry) => entry.sequence)).toEqual([8, 9, 10]);
    expect(session.state.hasMoreOlder).toBe(false);
    await session.loadMoreEvents();
    expect.verifySteps([]);
});

test('a chat shared for reading ignores every action that steers it', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({
            can_write: false,
            pending_ask: { kind: 'approval', call_id: 'c1' },
            state: 'waiting',
        }),
    );
    onRpc('muk_ai.session', '*', ({ method }) => {
        if (!['get_snapshot', 'dismiss_notifications'].includes(method)) {
            expect.step(method);
        }
    });
    const session = await openSession(1);
    session.state.input = 'hello';
    for (const action of [
        () => session.send(),
        () => session.stop(),
        () => session.attach([new File(['x'], 'x.txt')]),
        () => session.setAgent(2),
        () => session.regenerate(),
        () => session.unpin(),
        () => session.clear(),
        () => session.compact(),
        () => session.setApprovalMode('off'),
        () => session.approveTool(),
        () => session.rejectTool(),
        () => session.undoToEvent(1),
        () => session.forkAtEvent(1),
    ]) {
        await action();
    }
    expect.verifySteps([]);
    expect(session.state.input).toBe('hello');
});
