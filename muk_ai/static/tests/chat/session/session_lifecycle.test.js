import { describe, expect, test } from '@odoo/hoot';
import { Deferred } from '@odoo/hoot-mock';
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
        { event_id: 31, kind: 'user_message', content: 'hello', attachments: [] },
        { event_id: 32, kind: 'text', content: 'hi there' },
    ],
    pending_ask: null,
    view_context: { kind: 'record', model: 'res.partner', id: 3 },
    last_text: '',
    error_message: null,
    iteration_count: 1,
    total_input_tokens: 12,
    total_output_tokens: 8,
    last_input_tokens: 4,
    context_window: 8000,
    total_cost: 0.5,
    user_id: [4, 'Owner'],
    agent_id: [3, 'Helper'],
    override_approval_mode: false,
    effective_approval_mode: 'ask',
    pending_user_messages: [],
};

function snapshotFor(record, overrides = {}) {
    return {
        id: record.id,
        state: record.state,
        events: record.events || [],
        oldest_sequence: record.oldest_sequence ?? null,
        has_more_older: !!record.has_more_older,
        pending_ask: null,
        view_context: record.view_context || null,
        error_message: null,
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

async function mountSession() {
    let session;
    class Harness extends Component {
        static props = {};
        static template = xml`<div class="mk_harness"/>`;
        setup() {
            session = useAiSession({});
        }
    }
    mockService('notification', { add: () => {} });
    await mountWithCleanup(Harness, { props: {} });
    return session;
}

test('loading a null session id wipes every trace of the previous one', async () => {
    makeBusMock();
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(SESSION_RECORD));
    const session = await mountSession();
    await session.load(7);
    session.state.pendingAttachments = [{ id: 5, filename: 'a.txt' }];
    session.state.streamingText = 'partial';
    const result = await session.load(null);
    expect(result).toBe(null);
    expect(session.state.sessionId).toBe(null);
    expect(session.state.events).toEqual([]);
    expect(session.state.pendingAttachments).toEqual([]);
    expect(session.state.streamingText).toBe('');
    expect(session.state.loading).toBe(false);
});

test('a failing read surfaces the error and leaves no half-loaded session', async () => {
    makeBusMock();
    onRpc('muk_ai.session', 'read', () => {
        throw new Error('record gone');
    });
    const session = await mountSession();
    const result = await session.load(7);
    expect(result).toBe(null);
    expect(session.state.sessionId).toBe(7);
    expect(session.state.events).toEqual([]);
    expect(session.state.loading).toBe(false);
    expect(session.state.error).toMatch(/record gone/);
});

test('a superseded load never overwrites the session the user switched to', async () => {
    makeBusMock();
    const slow = new Deferred();
    onRpc('muk_ai.session', 'read', ({ args }) => {
        if (args[0][0] === 7) {
            return slow;
        }
        return [{ ...SESSION_RECORD, id: 8, name: 'Second' }];
    });
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshotFor({ ...SESSION_RECORD, id: args[0][0] }),
    );
    const session = await mountSession();
    const first = session.load(7);
    const second = session.load(8);
    slow.resolve([SESSION_RECORD]);
    await first;
    await second;
    expect(session.state.sessionId).toBe(8);
    expect(session.state.name).toBe('Second');
});

test('a snapshot failure still loads the record and shows an empty log', async () => {
    makeBusMock();
    onRpc('muk_ai.session', 'read', () => [SESSION_RECORD]);
    onRpc('muk_ai.session', 'get_snapshot', () => {
        throw new Error('snapshot unavailable');
    });
    const session = await mountSession();
    const record = await session.load(7);
    expect(record.id).toBe(7);
    expect(session.state.name).toBe('Demo session');
    expect(session.state.events).toEqual([]);
    expect(session.state.error).toBe(null);
});

test('loadMoreEvents drops events already present in the window', async () => {
    const record = {
        ...SESSION_RECORD,
        oldest_sequence: 100,
        has_more_older: true,
    };
    makeBusMock();
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    onRpc('muk_ai.session', 'fetch_events', () => ({
        events: [
            { event_id: 30, kind: 'text', content: 'older' },
            { event_id: 31, kind: 'user_message', content: 'hello', attachments: [] },
        ],
        oldest_sequence: 20,
        has_more_older: true,
    }));
    const session = await mountSession();
    await session.load(7);
    await session.loadMoreEvents();
    expect(session.state.events.map((e) => e.event_id)).toEqual([30, 31, 32]);
    expect(session.state.oldestSequence).toBe(20);
});

test('loadMoreEvents keeps the current window when a null oldest_sequence comes back', async () => {
    const record = {
        ...SESSION_RECORD,
        oldest_sequence: 100,
        has_more_older: true,
    };
    makeBusMock();
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    onRpc('muk_ai.session', 'fetch_events', () => ({
        events: [],
        oldest_sequence: null,
        has_more_older: false,
    }));
    const session = await mountSession();
    await session.load(7);
    await session.loadMoreEvents();
    expect(session.state.oldestSequence).toBe(100);
    expect(session.state.hasMoreOlder).toBe(false);
    expect(session.state.loadingOlder).toBe(false);
});

test('an older page landing after a session switch is discarded', async () => {
    const record = {
        ...SESSION_RECORD,
        oldest_sequence: 100,
        has_more_older: true,
    };
    makeBusMock();
    onRpc('muk_ai.session', 'read', ({ args }) => [{ ...record, id: args[0][0] }]);
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshotFor({ ...record, id: args[0][0], events: [] }),
    );
    const slow = new Deferred();
    onRpc('muk_ai.session', 'fetch_events', () => slow);
    const session = await mountSession();
    await session.load(7);
    const older = session.loadMoreEvents();
    await session.load(8);
    slow.resolve({
        events: [{ event_id: 1, kind: 'text', content: 'stale' }],
        oldest_sequence: 1,
        has_more_older: false,
    });
    await older;
    expect(session.state.sessionId).toBe(8);
    expect(session.state.events).toEqual([]);
    expect(session.state.oldestSequence).toBe(100);
});

test('loadMoreEvents is a noop without a loaded session', async () => {
    makeBusMock();
    let calls = 0;
    onRpc('muk_ai.session', 'fetch_events', () => {
        calls++;
        return { events: [], oldest_sequence: null, has_more_older: false };
    });
    const session = await mountSession();
    await session.loadMoreEvents();
    expect(calls).toBe(0);
});

test('renderMarkdown accepts a non-string body without throwing', async () => {
    makeBusMock();
    const session = await mountSession();
    expect(String(session.renderMarkdown(null))).toBe('');
    expect(String(session.renderMarkdown(42))).toMatch(/42/);
});

test('the markdown cache is bounded and re-renders evicted entries', async () => {
    makeBusMock();
    const session = await mountSession();
    const first = session.renderMarkdown('entry-0');
    expect(session.renderMarkdown('entry-0')).toBe(first);
    for (let i = 1; i <= 401; i++) {
        session.renderMarkdown(`entry-${i}`);
    }
    expect(session.renderMarkdown('entry-0')).not.toBe(first);
});
