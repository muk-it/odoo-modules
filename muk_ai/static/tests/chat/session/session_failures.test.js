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
    events: [{ event_id: 41, kind: 'user_message', content: 'hello', attachments: [] }],
    pending_ask: null,
    view_context: null,
    last_text: '',
    error_message: null,
    iteration_count: 1,
    total_input_tokens: 0,
    total_output_tokens: 0,
    last_input_tokens: 0,
    context_window: 8000,
    total_cost: 0,
    user_id: [4, 'Owner'],
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
    pending_user_messages: [],
};

function snapshotFor(record, overrides = {}) {
    return {
        id: record.id,
        state: record.state,
        events: record.events || [],
        oldest_sequence: null,
        has_more_older: false,
        pending_ask: record.pending_ask || null,
        view_context: record.view_context || null,
        error_message: null,
        iteration_count: record.iteration_count || 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_cost: 0,
        last_input_tokens: record.last_input_tokens || 0,
        context_window: record.context_window || 8000,
        override_approval_mode: false,
        effective_approval_mode: 'ask',
        pending_user_messages: record.pending_user_messages || [],
        ...overrides,
    };
}

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

function makeNotificationMock() {
    const messages = [];
    mockService('notification', { add: (msg) => messages.push(String(msg)) });
    return messages;
}

async function mountSession(record = SESSION_RECORD, options = {}) {
    let session;
    class Harness extends Component {
        static props = {};
        static template = xml`<div class="mk_harness"/>`;
        setup() {
            session = useAiSession(options);
        }
    }
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    await mountWithCleanup(Harness, { props: {} });
    await session.load(7);
    return session;
}

test('cancelQueued removes the entry and adopts the returned queue', async () => {
    makeBusMock();
    makeNotificationMock();
    const record = {
        ...SESSION_RECORD,
        state: 'running',
        pending_user_messages: [{ content: 'one' }, { content: 'two' }],
    };
    let cancelArgs = null;
    onRpc('muk_ai.session', 'cancel_queued', ({ args }) => {
        cancelArgs = args;
        return snapshotFor(record, { pending_user_messages: [{ content: 'two' }] });
    });
    const session = await mountSession(record);
    expect(session.state.pendingMessages).toHaveLength(2);
    await session.cancelQueued(0);
    expect(cancelArgs).toEqual([7, 0]);
    expect(session.state.pendingMessages).toEqual([{ content: 'two' }]);
});

test('a failed cancel puts the queued message back at its own position', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const record = {
        ...SESSION_RECORD,
        state: 'running',
        pending_user_messages: [
            { content: 'one' },
            { content: 'two' },
            { content: 'three' },
        ],
    };
    onRpc('muk_ai.session', 'cancel_queued', () => {
        throw new Error('already drained');
    });
    const session = await mountSession(record);
    await session.cancelQueued(1);
    expect(session.state.pendingMessages.map((m) => m.content)).toEqual([
        'one',
        'two',
        'three',
    ]);
    expect(notifications.some((m) => /Failed to cancel queued message/.test(m))).toBe(
        true,
    );
});

test('a queued message the server refuses to hold disappears from the queue', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const record = { ...SESSION_RECORD, state: 'running' };
    onRpc('muk_ai.session', 'enqueue_message', () => {
        throw new Error('drain already finished');
    });
    const session = await mountSession(record);
    session.onInputChange('do this next');
    await session.onSend();
    expect(session.state.pendingMessages).toEqual([]);
    expect(notifications.some((m) => /Failed to queue message/.test(m))).toBe(true);
});

test('cancelQueued without a loaded session is a noop', async () => {
    makeBusMock();
    makeNotificationMock();
    let calls = 0;
    onRpc('muk_ai.session', 'cancel_queued', () => {
        calls++;
        return snapshotFor(SESSION_RECORD);
    });
    const session = await mountSession();
    await session.load(null);
    await session.cancelQueued(0);
    expect(calls).toBe(0);
});

test('a nearly full context window warns once before the next send', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const record = { ...SESSION_RECORD, last_input_tokens: 5600 };
    onRpc('muk_ai.session', 'send_message', () => snapshotFor(record));
    let compacted = 0;
    onRpc('muk_ai.session', 'compact', () => {
        compacted++;
        return snapshotFor(record);
    });
    const session = await mountSession(record);
    session.onInputChange('carry on');
    await session.onSend();
    expect(compacted).toBe(0);
    expect(session.state.autoCompactPending).toBe(true);
    expect(notifications.filter((m) => /Context window at 70%/.test(m))).toHaveLength(
        1,
    );
    session.onInputChange('and again');
    await session.onSend();
    expect(notifications.filter((m) => /Context window at 70%/.test(m))).toHaveLength(
        1,
    );
});

test('rejecting a tool approval routes to reject_tool', async () => {
    makeBusMock();
    makeNotificationMock();
    const record = {
        ...SESSION_RECORD,
        state: 'waiting',
        pending_ask: { kind: 'approval', call_id: 'c1', tool: 'unlink' },
    };
    let rejectKwargs = null;
    onRpc('muk_ai.session', 'reject_tool', ({ kwargs }) => {
        rejectKwargs = kwargs;
        return snapshotFor(record, { state: 'running', pending_ask: null });
    });
    const session = await mountSession(record);
    await session.respondYesno('reject');
    expect(rejectKwargs.reason).toBe('');
    expect(session.state.status).toBe('running');
    expect(session.state.pendingAsk).toBe(null);
});

test('a failed answer restores the unanswered question', async () => {
    makeBusMock();
    makeNotificationMock();
    const record = {
        ...SESSION_RECORD,
        state: 'waiting',
        pending_ask: { kind: 'question', text: 'Which partner?' },
    };
    onRpc('muk_ai.session', 'answer', () => {
        throw new Error('session expired');
    });
    const session = await mountSession(record);
    session.onInputChange('Acme');
    await session.onSend();
    expect(session.state.status).toBe('waiting');
    expect(session.state.pendingAsk).toEqual({
        kind: 'question',
        text: 'Which partner?',
    });
    expect(session.state.events).toHaveLength(1);
    expect(session.state.error).toMatch(/session expired/);
});

test('a failing ui_action is reported instead of silently swallowed', async () => {
    const bus = makeBusMock();
    const notifications = makeNotificationMock();
    mockService('action', {
        doAction: () => {
            throw new Error('no such view');
        },
        loadAction: () => ({}),
    });
    await mountSession();
    bus.emit({
        session_id: 7,
        type: 'ui_action',
        payload: {
            action: { type: 'ir.actions.act_window', res_model: 'res.partner' },
        },
    });
    await animationFrame();
    expect(notifications.some((m) => /Failed to execute UI action/.test(m))).toBe(true);
});

test('a ui_action without a real action payload is ignored', async () => {
    const bus = makeBusMock();
    const notifications = makeNotificationMock();
    let dispatched = 0;
    mockService('action', {
        doAction: () => {
            dispatched++;
        },
        loadAction: () => ({}),
    });
    await mountSession();
    bus.emit({ session_id: 7, type: 'ui_action', payload: { action: 'muk_ai.foo' } });
    bus.emit({ session_id: 7, type: 'ui_action', payload: {} });
    await animationFrame();
    expect(dispatched).toBe(0);
    expect(notifications).toEqual([]);
});

test('a failing agent switch is reported and leaves the agent alone', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    onRpc('muk_ai.session', 'write', () => {
        throw new Error('agent archived');
    });
    const session = await mountSession();
    await session.setAgent(9, 'Analyst');
    expect(session.state.agentId).toBe(null);
    expect(notifications.some((m) => /Failed to change agent/.test(m))).toBe(true);
});

test('/agent is refused when no agent is available at all', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    let written = 0;
    onRpc('muk_ai.session', 'write', () => {
        written++;
        return true;
    });
    const session = await mountSession();
    session.onInputChange('/agent Helper');
    await session.onSend();
    expect(written).toBe(0);
    expect(notifications.some((m) => /No agents available/.test(m))).toBe(true);
});

test('/clear refreshes the sidebar after wiping the conversation', async () => {
    makeBusMock();
    makeNotificationMock();
    onRpc('muk_ai.session', 'clear', () =>
        snapshotFor(SESSION_RECORD, { state: 'new', events: [] }),
    );
    let refreshed = 0;
    const session = await mountSession(SESSION_RECORD, {
        onRefresh: () => {
            refreshed++;
        },
    });
    session.onInputChange('/clear');
    await session.onSend();
    expect(session.state.events).toEqual([]);
    expect(refreshed).toBe(1);
});

test('a failing /clear keeps the conversation and reports the error', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    onRpc('muk_ai.session', 'clear', () => {
        throw new Error('locked');
    });
    const session = await mountSession();
    session.onInputChange('/clear');
    await session.onSend();
    expect(session.state.events).toHaveLength(1);
    expect(notifications.some((m) => /Failed to clear session/.test(m))).toBe(true);
});

test('/compact is refused while a turn is running', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    let compacted = 0;
    onRpc('muk_ai.session', 'compact', () => {
        compacted++;
        return snapshotFor(SESSION_RECORD);
    });
    const session = await mountSession({ ...SESSION_RECORD, state: 'running' });
    session.onInputChange('/compact');
    await session.onSend();
    expect(compacted).toBe(0);
    expect(notifications.some((m) => /before compacting/.test(m))).toBe(true);
});

test('a failing /compact is reported via notification', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    onRpc('muk_ai.session', 'compact', () => {
        throw new Error('provider down');
    });
    const session = await mountSession();
    session.onInputChange('/compact');
    await session.onSend();
    expect(notifications.some((m) => /Failed to compact conversation/.test(m))).toBe(
        true,
    );
});

test('a failing /unpin keeps the pinned context visible', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const record = {
        ...SESSION_RECORD,
        view_context: { kind: 'record', model: 'res.partner', id: 3 },
    };
    onRpc('muk_ai.session', 'unpin_view_context', () => {
        throw new Error('read only');
    });
    const session = await mountSession(record);
    session.onInputChange('/unpin');
    await session.onSend();
    expect(session.state.viewContext).toEqual({
        kind: 'record',
        model: 'res.partner',
        id: 3,
    });
    expect(notifications.some((m) => /Failed to clear view context/.test(m))).toBe(
        true,
    );
});

test('a failing regenerate is reported and the log survives', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    onRpc('muk_ai.session', 'regenerate_last_turn', () => {
        throw new Error('nothing to redo');
    });
    const session = await mountSession();
    await session.onRegenerate();
    expect(session.state.events).toHaveLength(1);
    expect(notifications.some((m) => /Failed to regenerate/.test(m))).toBe(true);
});
