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
        { event_id: 11, kind: 'user_message', content: 'first', attachments: [] },
        { event_id: 12, kind: 'text', content: 'answer one' },
        { event_id: 13, kind: 'user_message', content: 'second', attachments: [] },
        { event_id: 14, kind: 'text', content: 'answer two' },
    ],
    pending_ask: null,
    view_context: null,
    last_text: '',
    error_message: null,
    iteration_count: 2,
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
        state: record.state,
        events: record.events || [],
        oldest_sequence: null,
        has_more_older: false,
        pending_ask: record.pending_ask || null,
        view_context: record.view_context || null,
        error_message: record.error_message || null,
        iteration_count: record.iteration_count || 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_cost: 0,
        last_input_tokens: 0,
        context_window: 8000,
        override_approval_mode: false,
        effective_approval_mode: 'ask',
        pending_user_messages: [],
        ...overrides,
    };
}

function makeBusMock() {
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
}

function makeDialogMock() {
    const opened = [];
    mockService('dialog', {
        add: (component, props) => {
            opened.push({ component, props });
            return () => {};
        },
    });
    return opened;
}

function makeNotificationMock() {
    const messages = [];
    mockService('notification', { add: (msg) => messages.push(String(msg)) });
    return messages;
}

async function mountSession(options = {}, record = SESSION_RECORD) {
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

test('runUndoToEvent asks to drop the target event and every later one', async () => {
    makeBusMock();
    makeNotificationMock();
    const dialogs = makeDialogMock();
    let undoArgs = null;
    onRpc('muk_ai.session', 'undo_to_event', ({ args }) => {
        undoArgs = args;
        return snapshotFor(SESSION_RECORD, {
            events: SESSION_RECORD.events.slice(0, 2),
        });
    });
    let refreshed = 0;
    const session = await mountSession({
        onRefresh: () => {
            refreshed++;
        },
    });
    const pending = session.runUndoToEvent(13);
    await Promise.resolve();
    expect(dialogs).toHaveLength(1);
    expect(String(dialogs[0].props.body)).toMatch(/\b2 event\(s\)/);
    dialogs[0].props.confirm();
    await pending;
    expect(undoArgs).toEqual([7, 13]);
    expect(session.state.events.map((e) => e.event_id)).toEqual([11, 12]);
    expect(refreshed).toBe(1);
});

test('runUndoToEvent counts the whole log when the event is not loaded', async () => {
    makeBusMock();
    makeNotificationMock();
    const dialogs = makeDialogMock();
    onRpc('muk_ai.session', 'undo_to_event', () => snapshotFor(SESSION_RECORD));
    const session = await mountSession();
    const pending = session.runUndoToEvent(999);
    await Promise.resolve();
    expect(String(dialogs[0].props.body)).toMatch(/\b4 event\(s\)/);
    dialogs[0].props.confirm();
    await pending;
});

test('cancelling the rewind dialog leaves the log untouched', async () => {
    makeBusMock();
    makeNotificationMock();
    const dialogs = makeDialogMock();
    let called = 0;
    onRpc('muk_ai.session', 'undo_to_event', () => {
        called++;
        return snapshotFor(SESSION_RECORD);
    });
    const session = await mountSession();
    const pending = session.runUndoToEvent(13);
    await Promise.resolve();
    dialogs[0].props.cancel();
    await pending;
    expect(called).toBe(0);
    expect(session.state.events).toHaveLength(4);
});

test('runUndoToEvent refuses to rewind a session that is still busy', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const dialogs = makeDialogMock();
    const session = await mountSession({}, { ...SESSION_RECORD, state: 'waiting' });
    await session.runUndoToEvent(13);
    expect(dialogs).toHaveLength(0);
    expect(notifications.some((m) => /before rewinding/.test(m))).toBe(true);
});

test('runUndoToEvent surfaces a backend failure without dropping events', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const dialogs = makeDialogMock();
    onRpc('muk_ai.session', 'undo_to_event', () => {
        throw new Error('sequence gone');
    });
    const session = await mountSession();
    const pending = session.runUndoToEvent(13);
    await Promise.resolve();
    dialogs[0].props.confirm();
    await pending;
    expect(session.state.events).toHaveLength(4);
    expect(notifications.some((m) => /Failed to rewind/.test(m))).toBe(true);
});

test('runForkAtEvent hands the new session id to the onForked callback', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    let forkArgs = null;
    onRpc('muk_ai.session', 'fork_at_event', ({ args }) => {
        forkArgs = args;
        return 88;
    });
    const forked = [];
    const session = await mountSession({
        onForked: (id) => forked.push(id),
    });
    await session.runForkAtEvent(13);
    expect(forkArgs).toEqual([7, 13]);
    expect(forked).toEqual([88]);
    expect(notifications.some((m) => /Forked into a new session/.test(m))).toBe(true);
});

test('runForkAtEvent refuses while the turn is still streaming', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    let called = 0;
    onRpc('muk_ai.session', 'fork_at_event', () => {
        called++;
        return 88;
    });
    const session = await mountSession({}, { ...SESSION_RECORD, state: 'running' });
    await session.runForkAtEvent(13);
    expect(called).toBe(0);
    expect(notifications.some((m) => /before forking/.test(m))).toBe(true);
});

test('runForkAtEvent reports a backend failure and skips the callback', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    onRpc('muk_ai.session', 'fork_at_event', () => {
        throw new Error('no such event');
    });
    const forked = [];
    const session = await mountSession({ onForked: (id) => forked.push(id) });
    await session.runForkAtEvent(13);
    expect(forked).toEqual([]);
    expect(notifications.some((m) => /Failed to fork/.test(m))).toBe(true);
});

test('/handover opens the user picker prefiltered by the typed name', async () => {
    makeBusMock();
    makeNotificationMock();
    const dialogs = makeDialogMock();
    const session = await mountSession();
    session.onInputChange('/handover Alice');
    await session.onSend();
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0].props.resModel).toBe('res.users');
    expect(dialogs[0].props.domain).toEqual([
        ['share', '=', false],
        ['active', '=', true],
        ['id', '!=', 4],
        ['name', 'ilike', 'Alice'],
    ]);
    expect(session.state.input).toBe('');
});

test('bare /handover opens the picker without a name filter', async () => {
    makeBusMock();
    makeNotificationMock();
    const dialogs = makeDialogMock();
    const session = await mountSession();
    session.onInputChange('/handover');
    await session.onSend();
    expect(dialogs[0].props.domain).toEqual([
        ['share', '=', false],
        ['active', '=', true],
        ['id', '!=', 4],
    ]);
});

test('picking a user in the handover dialog transfers the chat', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const dialogs = makeDialogMock();
    let handoverArgs = null;
    onRpc('muk_ai.session', 'action_handover', ({ args }) => {
        handoverArgs = args;
        return true;
    });
    const handed = [];
    const session = await mountSession({
        onHandedOver: (id) => handed.push(id),
    });
    session.openHandoverPicker();
    dialogs[0].props.onSelected([12]);
    await animationFrame();
    expect(handoverArgs).toEqual([7, 12]);
    expect(handed).toEqual([7]);
    expect(notifications.some((m) => /handed over/.test(m))).toBe(true);
});

test('handover dialog selection with no user is a noop', async () => {
    makeBusMock();
    makeNotificationMock();
    const dialogs = makeDialogMock();
    let called = 0;
    onRpc('muk_ai.session', 'action_handover', () => {
        called++;
        return true;
    });
    const session = await mountSession();
    session.openHandoverPicker();
    dialogs[0].props.onSelected([]);
    await animationFrame();
    expect(called).toBe(0);
});

test('handing over a compacting session is refused at selection time', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const dialogs = makeDialogMock();
    let called = 0;
    onRpc('muk_ai.session', 'action_handover', () => {
        called++;
        return true;
    });
    const session = await mountSession({}, { ...SESSION_RECORD, state: 'compacting' });
    session.openHandoverPicker();
    dialogs[0].props.onSelected([12]);
    await animationFrame();
    expect(called).toBe(0);
    expect(notifications.some((m) => /before handing it over/.test(m))).toBe(true);
});

test('onHandover surfaces a backend failure and keeps the session', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    const dialogs = makeDialogMock();
    onRpc('muk_ai.session', 'action_handover', () => {
        throw new Error('not allowed');
    });
    const handed = [];
    const session = await mountSession({ onHandedOver: (id) => handed.push(id) });
    session.openHandoverPicker();
    dialogs[0].props.onSelected([12]);
    await animationFrame();
    expect(handed).toEqual([]);
    expect(notifications.some((m) => /Failed to hand over/.test(m))).toBe(true);
});

test('runStopCompact stops an in-flight compaction and applies the snapshot', async () => {
    makeBusMock();
    makeNotificationMock();
    let stopArgs = null;
    onRpc('muk_ai.session', 'stop_compact', ({ args }) => {
        stopArgs = args;
        return snapshotFor(SESSION_RECORD, { state: 'done' });
    });
    const session = await mountSession({}, { ...SESSION_RECORD, state: 'compacting' });
    await session.runStopCompact();
    expect(stopArgs).toEqual([7]);
    expect(session.state.status).toBe('done');
});

test('runStopCompact is a noop when nothing is compacting', async () => {
    makeBusMock();
    makeNotificationMock();
    let called = 0;
    onRpc('muk_ai.session', 'stop_compact', () => {
        called++;
        return snapshotFor(SESSION_RECORD);
    });
    const session = await mountSession();
    await session.runStopCompact();
    expect(called).toBe(0);
});

test('runStopCompact surfaces a backend failure via notification', async () => {
    makeBusMock();
    const notifications = makeNotificationMock();
    onRpc('muk_ai.session', 'stop_compact', () => {
        throw new Error('already finished');
    });
    const session = await mountSession({}, { ...SESSION_RECORD, state: 'compacting' });
    await session.runStopCompact();
    expect(session.state.status).toBe('compacting');
    expect(notifications.some((m) => /Failed to stop compaction/.test(m))).toBe(true);
});
