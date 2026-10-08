import { advanceTime, expect, runAllTimers, test } from '@odoo/hoot';
import {
    getService,
    mountWebClient,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { sessionEventHandlers } from '@muk_ai/core/session/session';
import {
    defineAIModels,
    emit,
    emitEvent,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

test('the events of a chat land in its data and its stream', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ state: 'running' }));
    const session = await openSession(1);
    const cases = [
        ['text_delta', { delta: 'Hel' }, () => session.state.streamingText, 'Hel'],
        ['text_delta', { delta: 'lo' }, () => session.state.streamingText, 'Hello'],
        [
            'reasoning_delta',
            { delta: '## Planning\nreading **' },
            () => session.latestReasoningLine,
            'reading',
        ],
        [
            'tool_call_start',
            { call_id: 'c1', name: 'search_read' },
            () => session.state.streamingTools[0].name,
            'search_read',
        ],
        [
            'tool_call_args_delta',
            { call_id: 'c1', delta: '{"a"' },
            () => session.state.streamingTools[0].args,
            '{"a"',
        ],
        ['rename', { name: 'Renamed' }, () => session.data.name, 'Renamed'],
        [
            'view_context',
            { view_context: { kind: 'list', model: 'res.partner' } },
            () => session.data.view_context.model,
            'res.partner',
        ],
        [
            'queue',
            { pending: [{ content: 'later' }] },
            () => session.data.pending_user_messages.length,
            1,
        ],
        [
            'agent_switched',
            { agent_id: 2, agent_name: 'Analyst', effective_approval_mode: 'off' },
            () => [session.agentName, session.data.effective_approval_mode],
            ['Analyst', 'off'],
        ],
        [
            'state',
            {
                state: 'waiting',
                ask: { kind: 'question', call_id: 'c2' },
                total_cost: 0.5,
            },
            () => [
                session.data.pending_ask.call_id,
                session.data.total_cost,
                session.state.streamingText,
            ],
            ['c2', 0.5, ''],
        ],
        [
            'state',
            { state: 'error', error: 'boom' },
            () => [session.data.pending_ask, session.data.error_message],
            [null, 'boom'],
        ],
        ['state', { state: 'running' }, () => session.data.error_message, null],
        [
            'state',
            { state: 'waiting_schedule', resume_at: '2030-01-01 10:00:00' },
            () => session.data.resume_at,
            '2030-01-01 10:00:00',
        ],
        ['state', { state: 'done' }, () => session.data.resume_at, ''],
    ];
    for (const [type, payload, read, expected] of cases) {
        await emitEvent(1, type, payload);
        expect(read()).toEqual(expected, { message: type });
    }
    await emitEvent(2, 'rename', { name: 'Other chat' });
    expect(session.data.name).toBe('Renamed');
});

test('a logged event is added once and replaces the optimistic copy it confirms', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ state: 'running' }));
    const session = await openSession(1);
    session.state.events = [
        { kind: 'user_message', content: 'Hi', attachments: [], _clientKey: 'ck9' },
    ];
    session.state.streamingText = 'partial';
    const logged = {
        kind: 'user_message',
        content: 'Hi',
        attachments: [],
        event_id: 4,
        sequence: 4,
    };
    await emitEvent(1, 'log', logged);
    await emitEvent(1, 'log', logged);
    expect(session.state.events).toEqual([{ ...logged, _clientKey: 'ck9' }]);
    await emitEvent(1, 'log', {
        kind: 'text',
        content: 'Done',
        event_id: 5,
        sequence: 5,
    });
    expect(session.state.streamingText).toBe('');
    expect(session.turns.map((turn) => turn.role)).toEqual(['user', 'assistant']);
});

test('compaction progress rewrites its event in place', async () => {
    const progress = {
        kind: 'compact_progress',
        event_id: 9,
        sequence: 9,
        state: 'streaming',
    };
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ state: 'compacting', events: [progress] }),
    );
    const session = await openSession(1);
    await emitEvent(1, 'compact_delta', { event_id: 9, delta: 'Summ' });
    await emitEvent(1, 'compact_delta', { event_id: 9, delta: 'ary' });
    await emitEvent(1, 'compact_update', {
        event_id: 9,
        patch: { state: 'done', summary: 'All' },
    });
    expect(session.turns[0]).toMatchObject({
        streamedText: 'Summary',
        state: 'done',
        summary: 'All',
    });
});

test('an addon handles the event types it registered', async () => {
    sessionEventHandlers.add(
        'memory_saved',
        (payload, session) => (session.state.memory = payload.text),
    );
    const session = await openSession(1);
    await emitEvent(1, 'memory_saved', { text: 'likes tea' });
    expect(session.state.memory).toBe('likes tea');
});

test('a running chat that streams nothing for three seconds is flagged idle', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ state: 'running' }));
    const session = await openSession(1);
    await emitEvent(1, 'text_delta', { delta: 'x' });
    await advanceTime(2900);
    expect(session.state.streamIdle).toBe(false);
    await advanceTime(200);
    expect(session.state.streamIdle).toBe(true);
    await emitEvent(1, 'text_delta', { delta: 'y' });
    expect(session.state.streamIdle).toBe(false);
});

test('the state notifications of the user channel keep a shown chat current', async () => {
    const session = await openSession(1);
    await emit('muk_ai.session_state', {
        session_id: 1,
        name: 'From the sidebar',
        state: 'done',
        total_input_tokens: 1200,
        turn_usage: { input_tokens: 300 },
    });
    expect(session.data).toMatchObject({
        name: 'From the sidebar',
        total_input_tokens: 1200,
        turn_usage: { input_tokens: 300 },
    });
});

test('a write on the pinned record reloads its chatter when its form is on screen', async () => {
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.act_window',
        res_model: 'res.partner',
        res_id: serverState.partnerId,
        views: [[false, 'form']],
    });
    await openSession(1);
    await runAllTimers();
    onRpc('/mail/store', async (request) => {
        const { params } = await request.json();
        for (const [name, values] of params.fetch_params) {
            if (name === '/mail/thread/messages') {
                expect.step(`${values.thread_model} ${values.thread_id}`);
            }
        }
    });
    await emitEvent(1, 'record_written', { model: 'res.partner', id: 9999 });
    await runAllTimers();
    expect.verifySteps([]);
    await emitEvent(1, 'record_written', {
        model: 'res.partner',
        id: serverState.partnerId,
    });
    await runAllTimers();
    expect.verifySteps([`res.partner ${serverState.partnerId}`]);
});
