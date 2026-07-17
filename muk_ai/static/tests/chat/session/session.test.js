import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, xml } from '@odoo/owl';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { useAiSession } from '@muk_ai/chat/session/use_ai_session';

describe.current.tags('muk_ai');
defineMailModels();

const SESSION_RECORD = {
    id: 7,
    name: 'Demo session',
    state: 'done',
    events: [
        { kind: 'user_message', content: 'hello', attachments: [] },
        { kind: 'text', content: 'hi there' },
    ],
    pending_ask: null,
    view_context: null,
    last_text: '',
    error_message: null,
    iteration_count: 1,
    total_input_tokens: 42,
    total_output_tokens: 24,
    last_input_tokens: 10,
    context_window: 8000,
    total_cost: 0.12,
    agent_id: [3, 'Helper'],
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

const AGENTS = [
    { id: 1, name: 'Alpha', description: 'a', suggestions: [] },
    { id: 3, name: 'Helper', description: 'b', suggestions: ['draft?'] },
];

const SNAPSHOT_RUNNING = {
    state: 'running',
    events: [],
    pending_ask: null,
    view_context: null,
    error_message: null,
    iteration_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_cost: 0,
    last_input_tokens: 0,
    context_window: 8000,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

function makeBusMock() {
    const handlers = new Map();
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe(name, cb) {
            handlers.set(name, cb);
        },
        unsubscribe(name) {
            handlers.delete(name);
        },
    });
    return {
        emit(payload) {
            const cb = handlers.get('muk_ai.event');
            if (cb) {
                cb(payload);
            }
        },
    };
}

function makeHarness(options = {}) {
    let session;
    class Harness extends Component {
        static props = {};
        static template = xml`<div class="mk_harness"/>`;
        setup() {
            session = useAiSession(options);
        }
    }
    return { Harness, getSession: () => session };
}

function snapshotFor(record, overrides = {}) {
    return {
        state: record.state,
        events: record.events || [],
        oldest_sequence: record.oldest_sequence ?? null,
        has_more_older: !!record.has_more_older,
        pending_ask: record.pending_ask || null,
        view_context: record.view_context || null,
        error_message: record.error_message || null,
        iteration_count: record.iteration_count || 0,
        total_input_tokens: record.total_input_tokens || 0,
        total_output_tokens: record.total_output_tokens || 0,
        total_cost: record.total_cost || 0,
        last_input_tokens: record.last_input_tokens || 0,
        context_window: record.context_window || 0,
        override_approval_mode: record.override_approval_mode || false,
        effective_approval_mode: record.effective_approval_mode || 'ask',
        pending_user_messages: record.pending_user_messages || [],
        ...overrides,
    };
}

async function mountAndLoad(harness, sessionId = 7) {
    await mountWithCleanup(harness.Harness, { props: {} });
    const session = harness.getSession();
    if (sessionId !== null) {
        await session.load(sessionId);
    }
    return session;
}

test('load reads session and applies record to state', async () => {
    onRpc('muk_ai.session', 'read', ({ args }) => {
        expect(args[0]).toEqual([7]);
        return [SESSION_RECORD];
    });
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.state.sessionId).toBe(7);
    expect(session.state.name).toBe('Demo session');
    expect(session.state.status).toBe('done');
    expect(session.state.events.length).toBe(2);
    expect(session.state.agentId).toBe(3);
    expect(session.state.agentName).toBe('Helper');
    expect(session.state.totalCost).toBe(0.12);
    expect(session.state.loading).toBe(false);
});

test('load never bumps focusToken', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.state.focusToken).toBe(0);
    await session.load(9);
    expect(session.state.focusToken).toBe(0);
});

test('load is atomic: previous events stay visible until new snapshot arrives', async () => {
    const SECOND_RECORD = { ...SESSION_RECORD, id: 9, name: 'Second' };
    let resolveSecondRead;
    let resolveSecondSnapshot;
    const secondReadGate = new Promise((resolve) => {
        resolveSecondRead = () => resolve([SECOND_RECORD]);
    });
    const secondSnapshotGate = new Promise((resolve) => {
        resolveSecondSnapshot = () =>
            resolve(
                snapshotFor({
                    ...SECOND_RECORD,
                    events: [{ kind: 'text', content: 'second answer' }],
                }),
            );
    });
    onRpc('muk_ai.session', 'read', ({ args }) => {
        if (args[0][0] === 7) {
            return [SESSION_RECORD];
        }
        return secondReadGate;
    });
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) => {
        if (args[0] === 7) {
            return snapshotFor(SESSION_RECORD);
        }
        return secondSnapshotGate;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness, 7);
    expect(session.state.sessionId).toBe(7);
    expect(session.state.events.length).toBe(2);

    const loadPromise = session.load(9);
    expect(session.state.loading).toBe(true);
    expect(session.state.sessionId).toBe(7);
    expect(session.state.events.length).toBe(2);

    resolveSecondRead();
    await Promise.resolve();
    resolveSecondSnapshot();
    await loadPromise;

    expect(session.state.sessionId).toBe(9);
    expect(session.state.events.length).toBe(1);
    expect(session.state.events[0].content).toBe('second answer');
    expect(session.state.loading).toBe(false);
});

test('bus events arriving during load are applied once the snapshot lands', async () => {
    const SECOND_RECORD = { ...SESSION_RECORD, id: 9, name: 'Second' };
    let resolveSnapshot;
    const snapshotGate = new Promise((resolve) => {
        resolveSnapshot = () =>
            resolve(
                snapshotFor({
                    ...SECOND_RECORD,
                    events: [{ kind: 'text', content: 'from snapshot', event_id: 50 }],
                }),
            );
    });
    onRpc('muk_ai.session', 'read', ({ args }) =>
        args[0][0] === 7 ? [SESSION_RECORD] : [SECOND_RECORD],
    );
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        args[0] === 7 ? snapshotFor(SESSION_RECORD) : snapshotGate,
    );
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    const loading = session.load(9);
    bus.emit({
        session_id: 9,
        type: 'log',
        payload: { kind: 'text', content: 'from snapshot', event_id: 50 },
    });
    bus.emit({
        session_id: 9,
        type: 'log',
        payload: { kind: 'text', content: 'streamed during load', event_id: 51 },
    });
    resolveSnapshot();
    await loading;
    expect(session.state.sessionId).toBe(9);
    expect(session.state.events.filter((e) => e.event_id === 50)).toHaveLength(1);
    expect(session.state.events.filter((e) => e.event_id === 51)).toHaveLength(1);
});

test('optimistic user message keeps its render identity across the persisted swap', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'send_message', () => ({
        ...SNAPSHOT_RUNNING,
        events: [
            ...SESSION_RECORD.events,
            {
                kind: 'user_message',
                content: 'stable bubble',
                attachments: [],
                event_id: 77,
                at: '2026-07-02 22:00:00',
            },
        ],
    }));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('stable bubble');
    await session.onSend();
    const persisted = session.state.events.filter((e) => e.content === 'stable bubble');
    expect(persisted).toHaveLength(1);
    expect(persisted[0].event_id).toBe(77);
    expect(persisted[0]._clientKey).toMatch(/^ck\d+$/);
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: {
            kind: 'user_message',
            content: 'stable bubble',
            attachments: [],
            event_id: 77,
            at: '2026-07-02 22:00:00',
        },
    });
    expect(
        session.state.events.filter((e) => e.content === 'stable bubble'),
    ).toHaveLength(1);
});

test('bus echo replaces the optimistic twin in place instead of appending', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let resolveSend;
    const sendGate = new Promise((resolve) => {
        resolveSend = () => resolve({ ...SNAPSHOT_RUNNING, events: [] });
    });
    onRpc('muk_ai.session', 'send_message', () => sendGate);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('echo first');
    const sending = session.onSend();
    await animationFrame();
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: {
            kind: 'user_message',
            content: 'echo first',
            attachments: [],
            event_id: 88,
            at: '2026-07-02 22:00:01',
        },
    });
    const echoed = session.state.events.filter((e) => e.content === 'echo first');
    expect(echoed).toHaveLength(1);
    expect(echoed[0].event_id).toBe(88);
    expect(echoed[0]._clientKey).toMatch(/^ck\d+$/);
    resolveSend();
    await sending;
});

test('canSend is false while load is in flight', async () => {
    const SECOND_RECORD = { ...SESSION_RECORD, id: 9 };
    let resolveSecondRead;
    const secondReadGate = new Promise((resolve) => {
        resolveSecondRead = () => resolve([SECOND_RECORD]);
    });
    onRpc('muk_ai.session', 'read', ({ args }) => {
        if (args[0][0] === 7) {
            return [SESSION_RECORD];
        }
        return secondReadGate;
    });
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SECOND_RECORD));
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness, 7);
    session.state.input = 'hello';
    expect(session.canSend()).toBe(true);

    const loadPromise = session.load(9);
    expect(session.canSend()).toBe(false);

    resolveSecondRead();
    await loadPromise;
});

test('loadAgents fetches agents via search_read with suggestions field', async () => {
    let captured = null;
    onRpc('muk_ai.agent', 'search_read', ({ kwargs }) => {
        captured = kwargs;
        return AGENTS;
    });
    makeBusMock();
    const harness = makeHarness();
    await mountWithCleanup(harness.Harness, { props: {} });
    await harness.getSession().loadAgents();
    expect(harness.getSession().state.agents.length).toBe(2);
    expect(harness.getSession().state.agents[1].name).toBe('Helper');
    expect(captured.fields).toInclude('suggestions');
    expect(captured.domain).toEqual([['active', '=', true]]);
});

test('onSend posts to start for the first turn and flips status to running', async () => {
    const calls = [];
    onRpc('muk_ai.session', 'read', () => [
        { ...SESSION_RECORD, events: [], iteration_count: 0 },
    ]);
    onRpc('muk_ai.session', 'start', ({ args, kwargs }) => {
        calls.push({ method: 'start', args, kwargs });
        return { ...SNAPSHOT_RUNNING, state: 'running' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('hello world');
    await session.onSend();
    expect(calls).toHaveLength(1);
    expect(calls[0].args).toEqual([7, 'hello world']);
    expect(calls[0].kwargs.attachment_ids).toEqual([]);
    expect(session.state.status).toBe('running');
    expect(session.state.input).toBe('');
});

test('onSend routes subsequent turns through send_message', async () => {
    let sent = false;
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'send_message', ({ args }) => {
        sent = true;
        expect(args).toEqual([7, 'follow up']);
        return { ...SNAPSHOT_RUNNING, events: SESSION_RECORD.events };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('follow up');
    await session.onSend();
    expect(sent).toBe(true);
});

test('onSend queues through enqueue_message while a turn is running', async () => {
    const running = { ...SESSION_RECORD, state: 'running' };
    onRpc('muk_ai.session', 'read', () => [running]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(running));
    const calls = [];
    onRpc('muk_ai.session', 'enqueue_message', ({ args }) => {
        calls.push(args);
        return snapshotFor(running, {
            pending_user_messages: [{ content: args[1], attachment_ids: [] }],
        });
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('while running');
    await session.onSend();
    expect(calls).toEqual([[7, 'while running']]);
    expect(session.state.pendingMessages).toHaveLength(1);
    expect(session.state.pendingMessages[0].content).toBe('while running');
});

test('rejected queue attempt re-dispatches through the regular send path', async () => {
    const running = { ...SESSION_RECORD, state: 'running' };
    onRpc('muk_ai.session', 'read', () => [running]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(running));
    onRpc('muk_ai.session', 'enqueue_message', () =>
        snapshotFor(SESSION_RECORD, { queue_rejected_state: 'done' }),
    );
    const sends = [];
    onRpc('muk_ai.session', 'send_message', ({ args }) => {
        sends.push(args);
        return { ...SNAPSHOT_RUNNING, events: SESSION_RECORD.events };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('raced past the end');
    await session.onSend();
    expect(sends).toEqual([[7, 'raced past the end']]);
    expect(session.state.pendingMessages).toHaveLength(0);
    expect(session.state.status).toBe('running');
    expect(session.state.input).toBe('');
});

test('queue rejection re-send preserves a draft typed meanwhile', async () => {
    const running = { ...SESSION_RECORD, state: 'running' };
    onRpc('muk_ai.session', 'read', () => [running]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(running));
    let resolveEnqueue;
    const enqueueGate = new Promise((resolve) => {
        resolveEnqueue = () =>
            resolve(snapshotFor(SESSION_RECORD, { queue_rejected_state: 'done' }));
    });
    onRpc('muk_ai.session', 'enqueue_message', () => enqueueGate);
    onRpc('muk_ai.session', 'send_message', () => ({ ...SNAPSHOT_RUNNING }));
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('first message');
    const sending = session.onSend();
    await animationFrame();
    session.onInputChange('draft in progress');
    resolveEnqueue();
    await sending;
    expect(session.state.input).toBe('draft in progress');
});

test('send_message rejection re-dispatches once through a fresh send', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const sends = [];
    onRpc('muk_ai.session', 'send_message', ({ args }) => {
        sends.push(args);
        if (sends.length === 1) {
            return snapshotFor(SESSION_RECORD, { queue_rejected_state: 'done' });
        }
        return {
            ...SNAPSHOT_RUNNING,
            events: [
                ...SESSION_RECORD.events,
                { kind: 'user_message', content: args[1], attachments: [] },
            ],
        };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('flipped mid-flight');
    await session.onSend();
    expect(sends).toHaveLength(2);
    expect(sends[1]).toEqual([7, 'flipped mid-flight']);
    const optimistic = session.state.events.filter(
        (e) => e.content === 'flipped mid-flight',
    );
    expect(optimistic).toHaveLength(1);
});

test('bus log event with text kind appends to state.events and clears streamingText', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.streamingText = 'partial';
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: { kind: 'text', content: 'streamed answer' },
    });
    expect(session.state.events[session.state.events.length - 1]).toEqual({
        kind: 'text',
        content: 'streamed answer',
    });
    expect(session.state.streamingText).toBe('');
});

test('bus text_delta appends to streamingText without touching the log', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    const logSize = session.state.events.length;
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'He' } });
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'llo' } });
    expect(session.state.streamingText).toBe('Hello');
    expect(session.state.events.length).toBe(logSize);
});

test('tool_call_start registers a streaming tool and log kind tool_call clears it', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'tool_call_start',
        payload: { call_id: 'c1', name: 'search_read' },
    });
    expect(session.state.streamingTools).toHaveLength(1);
    expect(session.state.streamingTools[0].callId).toBe('c1');
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: {
            kind: 'tool_call',
            name: 'search_read',
            arguments: {},
            call_id: 'c1',
        },
    });
    expect(session.state.streamingTools).toHaveLength(0);
});

test('state bus event propagates status and pending ask', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'state',
        payload: {
            state: 'waiting',
            ask: { kind: 'question', text: 'continue?', call_id: 'a1' },
            last_input_tokens: 50,
            context_window: 8000,
        },
    });
    expect(session.state.status).toBe('waiting');
    expect(session.state.pendingAsk.text).toBe('continue?');
    expect(session.state.lastInputTokens).toBe(50);
});

test('onSend while waiting on a question dispatches to answer endpoint', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'question', text: 'your name?' },
        },
    ]);
    let answered = false;
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        answered = true;
        expect(args).toEqual([7, 'Alice']);
        return { ...SNAPSHOT_RUNNING, state: 'running' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.state.status).toBe('waiting');
    session.onInputChange('Alice');
    await session.onSend();
    expect(answered).toBe(true);
});

test('slash command /compact calls compact and skips send_message', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let sent = false;
    let compacted = false;
    onRpc('muk_ai.session', 'send_message', () => {
        sent = true;
        return SNAPSHOT_RUNNING;
    });
    onRpc('muk_ai.session', 'compact', ({ args }) => {
        compacted = true;
        expect(args).toEqual([7]);
        return { ...SNAPSHOT_RUNNING, state: 'done' };
    });
    makeBusMock();
    mockService('notification', { add: () => {} });
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/compact');
    await session.onSend();
    expect(compacted).toBe(true);
    expect(sent).toBe(false);
});

test('onSetAgent writes agent_id and updates state', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.agent', 'search_read', () => AGENTS);
    let written = null;
    onRpc('muk_ai.session', 'write', ({ args }) => {
        written = args;
        return true;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.loadAgents();
    await session.onSetAgent(1);
    expect(written).toEqual([[7], { agent_id: 1 }]);
    expect(session.state.agentId).toBe(1);
    expect(session.state.agentName).toBe('Alpha');
});

test('/agent <name> resolves the name and switches the agent', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.agent', 'search_read', () => AGENTS);
    let written = null;
    onRpc('muk_ai.session', 'write', ({ args }) => {
        written = args;
        return true;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.loadAgents();
    session.onInputChange('/agent Helper');
    await session.onSend();
    expect(written).toEqual([[7], { agent_id: 3 }]);
});

test('/agent <unknown> warns and does not switch', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.agent', 'search_read', () => AGENTS);
    let written = null;
    onRpc('muk_ai.session', 'write', ({ args }) => {
        written = args;
        return true;
    });
    const notifications = [];
    mockService('notification', {
        add: (msg, opts) => notifications.push({ msg: String(msg), type: opts?.type }),
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.loadAgents();
    session.onInputChange('/agent nope');
    await session.onSend();
    expect(written).toBe(null);
    expect(notifications.some((n) => /No agent matches/.test(n.msg))).toBe(true);
});

test('onSend surfaces backend errors into state.error and status', async () => {
    onRpc('muk_ai.session', 'read', () => [
        { ...SESSION_RECORD, events: [], iteration_count: 0 },
    ]);
    onRpc('muk_ai.session', 'start', () => {
        throw new Error('boom');
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('hi');
    await session.onSend();
    expect(session.state.status).toBe('error');
    expect(session.state.error).toMatch(/boom/);
});

test('onStop calls action_stop and applies snapshot', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, state: 'running' }]);
    let stopped = false;
    onRpc('muk_ai.session', 'action_stop', () => {
        stopped = true;
        return { ...SNAPSHOT_RUNNING, state: 'stopped' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onStop();
    expect(stopped).toBe(true);
    expect(session.state.status).toBe('stopped');
});

test('onStop surfaces errors via notification', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'action_stop', () => {
        throw new Error('stop-err');
    });
    makeBusMock();
    const notifications = [];
    mockService('notification', { add: (msg) => notifications.push(msg) });
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onStop();
    expect(notifications.some((n) => /stop-err/.test(String(n)))).toBe(true);
});

test('onRegenerate calls regenerate_last_turn and applies snapshot', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let called = false;
    onRpc('muk_ai.session', 'regenerate_last_turn', ({ args }) => {
        called = true;
        expect(args).toEqual([7]);
        return { ...SNAPSHOT_RUNNING, state: 'done' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onRegenerate();
    expect(called).toBe(true);
    expect(session.state.status).toBe('done');
});

test('onRegenerate is blocked while running or waiting', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, state: 'running' }]);
    let attempts = 0;
    onRpc('muk_ai.session', 'regenerate_last_turn', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onRegenerate();
    expect(attempts).toBe(0);
});

test('canRegenerate is false when log has no user_message', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, events: [] }]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.canRegenerate()).toBe(false);
});

test('canRegenerate is true when log has a user_message and status is done', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.canRegenerate()).toBe(true);
});

test('loadAgents swallows errors and resets agents to empty', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.agent', 'search_read', () => {
        throw new Error('down');
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.loadAgents();
    expect(session.state.agents).toEqual([]);
});

test('setApprovalMode calls set_approval_mode on the session', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let captured = null;
    onRpc('muk_ai.session', 'set_approval_mode', ({ args }) => {
        captured = args;
        return { ...SNAPSHOT_RUNNING, override_approval_mode: 'off' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.setApprovalMode('off');
    expect(captured).toEqual([7, 'off']);
});

test('cycleApprovalMode toggles the effective mode off <-> ask', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const captured = [];
    onRpc('muk_ai.session', 'set_approval_mode', ({ args }) => {
        captured.push(args[1]);
        return { ...SNAPSHOT_RUNNING, override_approval_mode: args[1] };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.effectiveApprovalMode = 'ask';
    await session.cycleApprovalMode();
    session.state.effectiveApprovalMode = 'off';
    await session.cycleApprovalMode();
    expect(captured).toEqual(['off', 'ask']);
});

test('runUnpin warns when no view context is pinned', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, view_context: null }]);
    const notifications = [];
    mockService('notification', {
        add: (msg, opts) => notifications.push({ msg: String(msg), type: opts?.type }),
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.runUnpin();
    expect(notifications.some((n) => /No view context/.test(n.msg))).toBe(true);
});

test('runUnpin calls unpin_view_context when context is set', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            view_context: { kind: 'record', model: 'res.partner', id: 1 },
        },
    ]);
    let called = false;
    onRpc('muk_ai.session', 'unpin_view_context', () => {
        called = true;
        return { ...SNAPSHOT_RUNNING, view_context: null };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.runUnpin();
    expect(called).toBe(true);
});

test('openPinnedContext dispatches ir.actions.act_window for record', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            view_context: { kind: 'record', model: 'res.partner', id: 99 },
        },
    ]);
    const actions = [];
    mockService('action', {
        doAction: (a) => {
            actions.push(a);
            return Promise.resolve();
        },
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.openPinnedContext();
    expect(actions).toHaveLength(1);
    expect(actions[0].res_id).toBe(99);
    expect(actions[0].view_mode).toBe('form');
});

test('openPinnedContext dispatches list view when kind is not record', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            view_context: {
                kind: 'list',
                model: 'sale.order',
                view_type: 'kanban',
                domain: [['state', '=', 'sale']],
            },
        },
    ]);
    const actions = [];
    mockService('action', {
        doAction: (a) => {
            actions.push(a);
            return Promise.resolve();
        },
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.openPinnedContext();
    expect(actions[0].view_mode).toBe('kanban');
    expect(actions[0].domain).toEqual([['state', '=', 'sale']]);
});

test('openPinnedContext noops when no context is set', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const actions = [];
    mockService('action', {
        doAction: (a) => {
            actions.push(a);
            return Promise.resolve();
        },
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.openPinnedContext();
    expect(actions).toEqual([]);
});

test('approveTool fires approve_tool RPC when awaiting approval', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'approval', call_id: 'c1' },
        },
    ]);
    let approved = false;
    onRpc('muk_ai.session', 'approve_tool', () => {
        approved = true;
        return { ...SNAPSHOT_RUNNING, state: 'running' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.approveTool();
    expect(approved).toBe(true);
});

test('approveForSession fires approve_for_session RPC when awaiting approval', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'approval', call_id: 'c1' },
        },
    ]);
    let called = false;
    onRpc('muk_ai.session', 'approve_for_session', () => {
        called = true;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.approveForSession();
    expect(called).toBe(true);
});

test('rejectTool fires reject_tool with reason kwarg', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'approval', call_id: 'c1' },
        },
    ]);
    let capturedKwargs = null;
    onRpc('muk_ai.session', 'reject_tool', ({ kwargs }) => {
        capturedKwargs = kwargs;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.rejectTool('too risky');
    expect(capturedKwargs.reason).toBe('too risky');
});

test('approveTool is a noop when not awaiting approval', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let attempts = 0;
    onRpc('muk_ai.session', 'approve_tool', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.approveTool();
    expect(attempts).toBe(0);
});

test('respondYesno routes to approve_tool when decision is approve', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'approval', call_id: 'c1' },
        },
    ]);
    let approved = false;
    onRpc('muk_ai.session', 'approve_tool', () => {
        approved = true;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.respondYesno('approve');
    expect(approved).toBe(true);
});

test('respondYesno routes to approve_for_session when decision is session', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'approval', call_id: 'c1' },
        },
    ]);
    let called = false;
    onRpc('muk_ai.session', 'approve_for_session', () => {
        called = true;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.respondYesno('session');
    expect(called).toBe(true);
});

test('respondYesno for non-approval kind translates into an answer option', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'question', text: 'Continue?' },
        },
    ]);
    let captured = null;
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        captured = args;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.respondYesno('approve');
    expect(captured).toEqual([7, 'Approve']);
});

test('toggleToolBlock toggles expanded state for a call id', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.isToolExpanded('c1')).toBe(false);
    session.toggleToolBlock('c1');
    expect(session.isToolExpanded('c1')).toBe(true);
    session.toggleToolBlock('c1');
    expect(session.isToolExpanded('c1')).toBe(false);
});

test('toggleToolBlock is a noop when callId is falsy', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.toggleToolBlock(null);
    expect(session.state.expandedTools).toEqual({});
});

test('renderedTurns groups log entries into user + assistant turns', async () => {
    const record = {
        ...SESSION_RECORD,
        events: [
            { kind: 'user_message', content: 'hello', attachments: [] },
            { kind: 'tool_call', name: 'search_read', call_id: 'c0', arguments: {} },
            { kind: 'tool_result', call_id: 'c0', result: '{}' },
            { kind: 'text', content: 'here you go' },
        ],
    };
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    const turns = session.renderedTurns();
    expect(turns.map((t) => t.role)).toEqual(['user', 'assistant']);
    expect(turns[1].blocks.map((b) => b.type)).toEqual(['tool', 'text']);
});

test('renderMarkdown returns markup-wrapped HTML', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    const html = String(session.renderMarkdown('**bold**'));
    expect(html).toMatch(/<strong>/);
});

test('renderMarkdown returns a stable markup object for the same text', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    const first = session.renderMarkdown('**bold**');
    const second = session.renderMarkdown('**bold**');
    expect(first).toBe(second);
    expect(session.renderMarkdown('*other*')).not.toBe(first);
});

test('canSend requires text; running allows queueing', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.canSend()).toBe(false);
    session.onInputChange('hi');
    expect(session.canSend()).toBe(true);
    session.state.status = 'running';
    expect(session.canSend()).toBe(true);
});

test('canStop only when running', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, state: 'running' }]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.canStop()).toBe(true);
    session.state.status = 'done';
    expect(session.canStop()).toBe(false);
});

test('canAttach needs sessionId and not running', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.canAttach()).toBe(true);
    session.state.status = 'running';
    expect(session.canAttach()).toBe(false);
});

test('setScrollCallback is invoked on requestScroll triggers', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    let calls = 0;
    session.setScrollCallback(() => calls++);
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: { kind: 'text', content: 'x' },
    });
    expect(calls).toBeGreaterThan(0);
});

test('maybeAutoCompact fires /compact silently when ratio above auto threshold', async () => {
    const record = {
        ...SESSION_RECORD,
        last_input_tokens: 7700,
        context_window: 8000,
        events: [{ kind: 'user_message', content: 'old', attachments: [] }],
        iteration_count: 2,
    };
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    let compacted = false;
    onRpc('muk_ai.session', 'compact', () => {
        compacted = true;
        return { ...SNAPSHOT_RUNNING, last_input_tokens: 10, state: 'done' };
    });
    onRpc('muk_ai.session', 'send_message', () => SNAPSHOT_RUNNING);
    mockService('notification', { add: () => {} });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('follow up');
    await session.onSend();
    expect(compacted).toBe(true);
});

test('/help slash command appends a summary entry without calling send', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let sent = false;
    onRpc('muk_ai.session', 'send_message', () => {
        sent = true;
        return SNAPSHOT_RUNNING;
    });
    mockService('notification', { add: () => {} });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/help');
    await session.onSend();
    expect(sent).toBe(false);
    const last = session.state.events[session.state.events.length - 1];
    expect(last.name).toBe('/help');
});

test('/unpin slash triggers unpin_view_context when context exists', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            view_context: { kind: 'record', model: 'res.partner', id: 1 },
        },
    ]);
    let unpinned = false;
    onRpc('muk_ai.session', 'unpin_view_context', () => {
        unpinned = true;
        return { ...SNAPSHOT_RUNNING, view_context: null };
    });
    mockService('notification', { add: () => {} });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/unpin');
    await session.onSend();
    expect(unpinned).toBe(true);
});

test('bus tool_call_args_delta accumulates on the matching streaming tool', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'tool_call_start',
        payload: { call_id: 'c9', name: 't' },
    });
    bus.emit({
        session_id: 7,
        type: 'tool_call_args_delta',
        payload: { call_id: 'c9', delta: '{"a":' },
    });
    bus.emit({
        session_id: 7,
        type: 'tool_call_args_delta',
        payload: { call_id: 'c9', delta: '1}' },
    });
    expect(session.state.streamingTools[0].argsBuffer).toBe('{"a":1}');
});

test('bus ui_action dispatches via action service', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const actions = [];
    mockService('action', {
        doAction: (a) => {
            actions.push(a);
            return Promise.resolve();
        },
    });
    const bus = makeBusMock();
    const harness = makeHarness();
    await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'ui_action',
        payload: {
            action: { type: 'ir.actions.act_window', res_model: 'res.partner' },
        },
    });
    expect(actions).toHaveLength(1);
    expect(actions[0].res_model).toBe('res.partner');
});

test('bus view_context event updates state', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'view_context',
        payload: { view_context: { kind: 'record', model: 'res.partner', id: 4 } },
    });
    expect(session.state.viewContext.model).toBe('res.partner');
});

test('bus event ignored when session_id differs', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    const before = session.state.events.length;
    bus.emit({
        session_id: 999,
        type: 'log',
        payload: { kind: 'text', content: 'ignored' },
    });
    expect(session.state.events.length).toBe(before);
});

test('applySnapshot replaces state from a server snapshot', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.applySnapshot({
        ...SNAPSHOT_RUNNING,
        state: 'done',
        events: [{ kind: 'text', content: 'final' }],
        total_cost: 0.5,
    });
    expect(session.state.status).toBe('done');
    expect(session.state.totalCost).toBe(0.5);
    expect(session.state.events.at(-1).content).toBe('final');
});

test('onAttachFiles uploads base64 payloads and appends to pendingAttachments', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let payloads = null;
    onRpc('muk_ai.session', 'upload_attachments', ({ args }) => {
        payloads = args[1];
        return [{ id: 101, filename: 'a.txt', mimetype: 'text/plain', size: 1 }];
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onAttachFiles([new File(['hi'], 'a.txt', { type: 'text/plain' })]);
    expect(session.state.pendingAttachments).toHaveLength(1);
    expect(session.state.pendingAttachments[0].filename).toBe('a.txt');
    expect(payloads[0].filename).toBe('a.txt');
});

test('onAttachFiles is a noop when files array is empty', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let attempts = 0;
    onRpc('muk_ai.session', 'upload_attachments', () => {
        attempts++;
        return [];
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onAttachFiles([]);
    expect(attempts).toBe(0);
});

test('onRemoveAttachment filters the attachment and calls discard RPC', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let discardArgs = null;
    onRpc('muk_ai.session', 'discard_attachments', ({ args }) => {
        discardArgs = args;
        return true;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.pendingAttachments = [
        { id: 1, filename: 'a' },
        { id: 2, filename: 'b' },
    ];
    await session.onRemoveAttachment(1);
    expect(session.state.pendingAttachments.map((a) => a.id)).toEqual([2]);
    expect(discardArgs).toEqual([7, [1]]);
});

test('setAgent writes agent_id directly and updates local state', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let written = null;
    onRpc('muk_ai.session', 'write', ({ args }) => {
        written = args;
        return true;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.setAgent(5, 'Bravo');
    expect(written).toEqual([[7], { agent_id: 5 }]);
    expect(session.state.agentName).toBe('Bravo');
});

test('setAgent with null agentId clears the agent on the record', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let written = null;
    onRpc('muk_ai.session', 'write', ({ args }) => {
        written = args;
        return true;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.setAgent(null);
    expect(written[1].agent_id).toBe(false);
    expect(session.state.agentId).toBe(null);
});

test('answerWithOption forwards to onSend with the option as input', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'question', text: 'Color?' },
        },
    ]);
    let answered = null;
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        answered = args;
        return { ...SNAPSHOT_RUNNING, state: 'running' };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.answerWithOption('red');
    expect(answered).toEqual([7, 'red']);
});

test('answerWithOption is a noop during running status', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, state: 'running' }]);
    let attempts = 0;
    onRpc('muk_ai.session', 'answer', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.answerWithOption('blue');
    expect(attempts).toBe(0);
});

test('copyText writes to clipboard when navigator.clipboard is available', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    mockService('notification', { add: () => {} });
    const writes = [];
    const originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: (t) => {
                writes.push(t);
                return Promise.resolve();
            },
        },
    });
    try {
        const harness = makeHarness();
        const session = await mountAndLoad(harness);
        session.copyText('some text');
        expect(writes).toEqual(['some text']);
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: originalClipboard,
        });
    }
});

test('copyText is a noop when text is empty', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    mockService('notification', { add: () => {} });
    const writes = [];
    const originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: (t) => {
                writes.push(t);
                return Promise.resolve();
            },
        },
    });
    try {
        const harness = makeHarness();
        const session = await mountAndLoad(harness);
        session.copyText('');
        session.copyText(null);
        expect(writes).toEqual([]);
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: originalClipboard,
        });
    }
});

test('bus error state snapshot surfaces error message', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'state',
        payload: { state: 'error', error: 'boom' },
    });
    expect(session.state.status).toBe('error');
    expect(session.state.error).toBe('boom');
});

test('onSend is a noop while session is running', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, state: 'running' }]);
    let attempts = 0;
    onRpc('muk_ai.session', 'send_message', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    onRpc('muk_ai.session', 'start', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('hi');
    await session.onSend();
    expect(attempts).toBe(0);
});

test('onSend emits optimistic answer entry when waiting on a question', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'question', text: 'Which?' },
        },
    ]);
    onRpc('muk_ai.session', 'answer', () => SNAPSHOT_RUNNING);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('pick one');
    await session.onSend();
    const last = session.state.events.find((e) => e.kind === 'answer');
    expect(last).not.toBe(undefined);
    expect(last.answer).toBe('pick one');
});

test('onSend refuses empty input', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let attempts = 0;
    onRpc('muk_ai.session', 'send_message', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    onRpc('muk_ai.session', 'start', () => {
        attempts++;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('   ');
    await session.onSend();
    expect(attempts).toBe(0);
});

test('unknown slash command falls through to normal send', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let sent = false;
    onRpc('muk_ai.session', 'send_message', () => {
        sent = true;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/bogus stuff here');
    await session.onSend();
    expect(sent).toBe(true);
});

test('bare slash prefix with no word falls through to normal send', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let sent = false;
    onRpc('muk_ai.session', 'send_message', () => {
        sent = true;
        return SNAPSHOT_RUNNING;
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/   ');
    await session.onSend();
    expect(sent).toBe(true);
});

test('onInputChange updates input state directly', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('hello');
    expect(session.state.input).toBe('hello');
});

test('setApprovalMode swallows errors via notification', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'set_approval_mode', () => {
        throw new Error('boom');
    });
    const notifications = [];
    mockService('notification', { add: (msg) => notifications.push(String(msg)) });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.setApprovalMode('off');
    expect(notifications.some((m) => /approval mode/.test(m))).toBe(true);
});

test('approveTool swallows RPC errors via notification', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            state: 'waiting',
            pending_ask: { kind: 'approval', call_id: 'c1' },
        },
    ]);
    onRpc('muk_ai.session', 'approve_tool', () => {
        throw new Error('bad');
    });
    const notifications = [];
    mockService('notification', { add: (msg) => notifications.push(String(msg)) });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.approveTool();
    expect(notifications.some((m) => /approve/.test(m))).toBe(true);
});

test('openPinnedContext surfaces action errors via notification', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            view_context: { kind: 'record', model: 'res.partner', id: 1 },
        },
    ]);
    const notifications = [];
    mockService('action', {
        doAction: () => {
            throw new Error('no route');
        },
    });
    mockService('notification', { add: (msg) => notifications.push(String(msg)) });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.openPinnedContext();
    expect(notifications.some((m) => /Failed to open/.test(m))).toBe(true);
});

test('onAttachFiles surfaces upload errors via notification', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'upload_attachments', () => {
        throw new Error('disk full');
    });
    const notifications = [];
    mockService('notification', { add: (msg) => notifications.push(String(msg)) });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.onAttachFiles([new File(['x'], 'a.txt', { type: 'text/plain' })]);
    expect(notifications.some((m) => /upload failed/i.test(m))).toBe(true);
});

test('/clear calls clear immediately without a confirmation dialog', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    let cleared = false;
    onRpc('muk_ai.session', 'clear', () => {
        cleared = true;
        return { ...SNAPSHOT_RUNNING, state: 'new' };
    });
    const dialogs = [];
    mockService('dialog', {
        add: (Component, props) => {
            dialogs.push(props);
            return () => {};
        },
    });
    mockService('notification', { add: () => {} });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/clear');
    await session.onSend();
    expect(dialogs).toHaveLength(0);
    expect(cleared).toBe(true);
});

test('loadMoreEvents prepends older window and updates oldestSequence', async () => {
    const record = {
        ...SESSION_RECORD,
        events: [
            { kind: 'user_message', content: 'recent-1', attachments: [] },
            { kind: 'text', content: 'recent-2' },
        ],
        oldest_sequence: 100,
        has_more_older: true,
    };
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    let fetchArgs = null;
    onRpc('muk_ai.session', 'fetch_events', ({ args, kwargs }) => {
        fetchArgs = { args, kwargs };
        return {
            events: [
                { kind: 'user_message', content: 'older-1', attachments: [] },
                { kind: 'text', content: 'older-2' },
            ],
            oldest_sequence: 50,
            has_more_older: false,
        };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    expect(session.state.hasMoreOlder).toBe(true);
    expect(session.state.oldestSequence).toBe(100);
    await session.loadMoreEvents();
    expect(fetchArgs.args).toEqual([7]);
    expect(fetchArgs.kwargs.before_sequence).toBe(100);
    expect(fetchArgs.kwargs.limit).toBe(100);
    expect(session.state.events.length).toBe(4);
    expect(session.state.events[0].content).toBe('older-1');
    expect(session.state.events[3].content).toBe('recent-2');
    expect(session.state.oldestSequence).toBe(50);
    expect(session.state.hasMoreOlder).toBe(false);
});

test('loadMoreEvents is a noop when hasMoreOlder is false', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    let calls = 0;
    onRpc('muk_ai.session', 'fetch_events', () => {
        calls++;
        return { events: [], oldest_sequence: null, has_more_older: false };
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    await session.loadMoreEvents();
    expect(calls).toBe(0);
});

test('/clear while running is a noop (onSend bails before slash dispatch)', async () => {
    onRpc('muk_ai.session', 'read', () => [{ ...SESSION_RECORD, state: 'running' }]);
    const dialogs = [];
    mockService('dialog', {
        add: (Component, props) => {
            dialogs.push(props);
            return () => {};
        },
    });
    makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.onInputChange('/clear');
    await session.onSend();
    expect(dialogs).toEqual([]);
});

test('popout fires before doAction when surface is fullscreen', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const calls = [];
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => {
            calls.push({ kind: 'open', id });
        },
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('action', {
        doAction: (a) => {
            calls.push({ kind: 'doAction', a });
            return Promise.resolve();
        },
    });
    const bus = makeBusMock();
    const harness = makeHarness({ surface: 'fullscreen' });
    const session = await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'ui_action',
        payload: {
            action: { type: 'ir.actions.act_window', res_model: 'res.partner' },
        },
    });
    await Promise.resolve();
    expect(calls).toHaveLength(2);
    expect(calls[0].kind).toBe('open');
    expect(calls[0].id).toBe(7);
    expect(calls[1].kind).toBe('doAction');
    expect(session.state.sessionId).toBe(7);
});

test('popout is skipped when surface is window', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    const opened = [];
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => {
            opened.push(id);
        },
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    const actions = [];
    mockService('action', {
        doAction: (a) => {
            actions.push(a);
            return Promise.resolve();
        },
    });
    const bus = makeBusMock();
    const harness = makeHarness({ surface: 'window' });
    await mountAndLoad(harness);
    bus.emit({
        session_id: 7,
        type: 'ui_action',
        payload: {
            action: { type: 'ir.actions.act_window', res_model: 'res.partner' },
        },
    });
    await Promise.resolve();
    expect(opened).toEqual([]);
    expect(actions).toHaveLength(1);
});

test('popout is skipped when no active session is loaded', async () => {
    onRpc('muk_ai.session', 'read', () => [
        {
            ...SESSION_RECORD,
            view_context: { kind: 'record', model: 'res.partner', id: 99 },
        },
    ]);
    const opened = [];
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => {
            opened.push(id);
        },
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('action', { doAction: () => Promise.resolve() });
    makeBusMock();
    const harness = makeHarness({ surface: 'fullscreen' });
    await mountWithCleanup(harness.Harness, { props: {} });
    const session = harness.getSession();
    session.state.sessionId = null;
    session.state.viewContext = { kind: 'record', model: 'res.partner', id: 99 };
    await session.openPinnedContext();
    expect(opened).toEqual([]);
});

test('streamIdle stays false while deltas keep arriving', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'partial' } });
    expect(session.state.streamIdle).toBe(false);
    expect(session.state.streamingText).toBe('partial');
});

test('streamIdle flips to true after STREAM_IDLE_MS without deltas', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'pause...' } });
    expect(session.state.streamIdle).toBe(false);
    await new Promise((r) => setTimeout(r, 3300));
    expect(session.state.streamIdle).toBe(true);
});

test('streamIdle resets to false on a new delta', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'a' } });
    await new Promise((r) => setTimeout(r, 3300));
    expect(session.state.streamIdle).toBe(true);
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'b' } });
    expect(session.state.streamIdle).toBe(false);
});

test('streamIdle clears when status leaves running', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    bus.emit({ session_id: 7, type: 'text_delta', payload: { delta: 'done' } });
    await new Promise((r) => setTimeout(r, 3300));
    expect(session.state.streamIdle).toBe(true);
    bus.emit({ session_id: 7, type: 'state', payload: { state: 'done' } });
    expect(session.state.streamIdle).toBe(false);
});

test('tool_call log bumps streamIdle activity', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    session.state.streamIdle = true;
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: {
            kind: 'tool_call',
            name: 'search_read',
            arguments: {},
            call_id: 'c9',
        },
    });
    expect(session.state.streamIdle).toBe(false);
});

test('tool_result log bumps streamIdle activity', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    session.state.streamIdle = true;
    bus.emit({
        session_id: 7,
        type: 'log',
        payload: {
            kind: 'tool_result',
            name: 'search_read',
            call_id: 'c9',
            result: '[]',
        },
    });
    expect(session.state.streamIdle).toBe(false);
});

test('tool_call_result completes only the matching streaming tool card', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    bus.emit({
        session_id: 7,
        type: 'tool_call_start',
        payload: { call_id: 'c1', name: 'search_read' },
    });
    bus.emit({
        session_id: 7,
        type: 'tool_call_start',
        payload: { call_id: 'c2', name: 'write' },
    });
    bus.emit({
        session_id: 7,
        type: 'tool_call_result',
        payload: { call_id: 'c1', name: 'search_read', result: '[]' },
    });
    const [first, second] = session.state.streamingTools;
    expect(first.done).toBe(true);
    expect(first.result).toBe('[]');
    expect(second.done).toBe(undefined);
    expect(session.state.streamingTools.length).toBe(2);
});

test('tool_call_result without call_id leaves streaming tools untouched', async () => {
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const bus = makeBusMock();
    const harness = makeHarness();
    const session = await mountAndLoad(harness);
    session.state.status = 'running';
    bus.emit({
        session_id: 7,
        type: 'tool_call_start',
        payload: { call_id: 'c1', name: 'search_read' },
    });
    bus.emit({
        session_id: 7,
        type: 'tool_call_result',
        payload: { result: '[]' },
    });
    expect(session.state.streamingTools[0].done).toBe(undefined);
});
