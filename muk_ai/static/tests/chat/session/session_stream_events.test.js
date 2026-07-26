import { describe, expect, test } from '@odoo/hoot';
import { Component, xml } from '@odoo/owl';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { useAiSession } from '@muk_ai/chat/session/use_ai_session';

describe.current.tags('muk_ai');
defineMailModels();

const { DateTime } = luxon;

const SESSION_RECORD = {
    id: 7,
    name: 'Demo session',
    state: 'running',
    events: [
        { event_id: 21, kind: 'user_message', content: 'go', attachments: [] },
        { event_id: 22, kind: 'compact_progress', summary: 'part', streamed_text: 'A' },
    ],
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
        oldest_sequence: null,
        has_more_older: false,
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
        pending_user_messages: [],
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

async function mountSession(record = SESSION_RECORD) {
    let session;
    class Harness extends Component {
        static props = {};
        static template = xml`<div class="mk_harness"/>`;
        setup() {
            session = useAiSession({});
        }
    }
    onRpc('muk_ai.session', 'read', () => [record]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotFor(record));
    mockService('notification', { add: () => {} });
    await mountWithCleanup(Harness, { props: {} });
    await session.load(7);
    return session;
}

test('reasoning deltas accumulate and the last cleaned line is exposed', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'reasoning_delta',
        payload: { delta: '## Plan\n\n- **step one**\n' },
    });
    bus.emit({
        session_id: 7,
        type: 'reasoning_delta',
        payload: { delta: '\n> weighing options**' },
    });
    expect(session.state.streamingReasoning).toBe(
        '## Plan\n\n- **step one**\n\n> weighing options**',
    );
    expect(session.latestReasoningLine()).toBe('weighing options');
});

test('an empty reasoning delta neither appends nor bumps activity', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({ session_id: 7, type: 'reasoning_delta', payload: { delta: '' } });
    bus.emit({ session_id: 7, type: 'reasoning_delta', payload: {} });
    expect(session.state.streamingReasoning).toBe('');
    expect(session.latestReasoningLine()).toBe('');
});

test('reasoning made only of markdown decoration yields no line', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'reasoning_delta',
        payload: { delta: '###\n\n***\n\n---' },
    });
    expect(session.latestReasoningLine()).toBe('');
});

test('a null bus payload is ignored', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit(null);
    expect(session.state.events).toHaveLength(2);
});

test('rename bus event renames the open session', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({ session_id: 7, type: 'rename', payload: { name: 'Renamed' } });
    expect(session.state.name).toBe('Renamed');
    bus.emit({ session_id: 7, type: 'rename', payload: { name: '' } });
    expect(session.state.name).toBe('Renamed');
});

test('agent_switched bus event swaps agent and approval mode', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'agent_switched',
        payload: { agent_id: 9, agent_name: 'Analyst', effective_approval_mode: 'off' },
    });
    expect(session.state.agentId).toBe(9);
    expect(session.state.agentName).toBe('Analyst');
    expect(session.state.effectiveApprovalMode).toBe('off');
});

test('agent_switched without an agent clears the selection', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({ session_id: 7, type: 'agent_switched', payload: {} });
    expect(session.state.agentId).toBe(null);
    expect(session.state.agentName).toBe('');
    expect(session.state.effectiveApprovalMode).toBe('ask');
});

test('queue bus event replaces the pending message list', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'queue',
        payload: { pending: [{ content: 'later', attachment_ids: [] }] },
    });
    expect(session.state.pendingMessages).toEqual([
        { content: 'later', attachment_ids: [] },
    ]);
    bus.emit({ session_id: 7, type: 'queue', payload: {} });
    expect(session.state.pendingMessages).toEqual([]);
});

test('compact_delta streams into the matching compact_progress event only', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'compact_delta',
        payload: { event_id: 22, delta: 'BC' },
    });
    expect(session.state.events[1].streamed_text).toBe('ABC');
    expect(session.state.events[0].streamed_text).toBe(undefined);
});

test('compact_delta without an id or body leaves the log untouched', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({ session_id: 7, type: 'compact_delta', payload: { delta: 'X' } });
    bus.emit({ session_id: 7, type: 'compact_delta', payload: { event_id: 22 } });
    expect(session.state.events[1].streamed_text).toBe('A');
});

test('compact_delta targeting a non-compact event changes nothing', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'compact_delta',
        payload: { event_id: 21, delta: 'X' },
    });
    expect(session.state.events[0].content).toBe('go');
    expect(session.state.events[0].streamed_text).toBe(undefined);
});

test('compact_update patches the compact_progress event in place', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'compact_update',
        payload: { event_id: 22, patch: { summary: 'final', done: true } },
    });
    expect(session.state.events[1].summary).toBe('final');
    expect(session.state.events[1].done).toBe(true);
    expect(session.state.events[1].streamed_text).toBe('A');
});

test('compact_update without an event id is ignored', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'compact_update',
        payload: { patch: { summary: 'nope' } },
    });
    expect(session.state.events[1].summary).toBe('part');
});

test('state bus event carries cost and a scheduled resume time', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'state',
        payload: {
            state: 'waiting_schedule',
            total_cost: 1.25,
            resume_at: '2026-07-26 12:00:00',
        },
    });
    expect(session.state.totalCost).toBe(1.25);
    expect(session.state.resumeAt).toBe('2026-07-26 12:00:00');
});

test('leaving waiting_schedule clears the resume time', async () => {
    const bus = makeBusMock();
    const session = await mountSession();
    bus.emit({
        session_id: 7,
        type: 'state',
        payload: { state: 'waiting_schedule', resume_at: '2026-07-26 12:00:00' },
    });
    bus.emit({ session_id: 7, type: 'state', payload: { state: 'running' } });
    expect(session.state.resumeAt).toBe('');
    expect(session.state.status).toBe('running');
});

test('a luxon resume_at is normalised to an ISO UTC string', async () => {
    makeBusMock();
    const session = await mountSession();
    session.applySnapshot(
        snapshotFor(SESSION_RECORD, {
            resume_at: DateTime.fromISO('2026-07-26T10:30:00Z', { zone: 'utc' }),
        }),
    );
    expect(session.state.resumeAt).toMatch(/^2026-07-26T10:30:00\.000(Z|\+00:00)$/);
});

test('an invalid luxon resume_at normalises to an empty string', async () => {
    makeBusMock();
    const session = await mountSession();
    session.applySnapshot(
        snapshotFor(SESSION_RECORD, { resume_at: DateTime.invalid('unset') }),
    );
    expect(session.state.resumeAt).toBe('');
});

test('a non-string non-luxon resume_at is stringified', async () => {
    makeBusMock();
    const session = await mountSession();
    session.applySnapshot(snapshotFor(SESSION_RECORD, { resume_at: 1750000000 }));
    expect(session.state.resumeAt).toBe('1750000000');
});

test('applySnapshot ignores a snapshot addressed to another session', async () => {
    makeBusMock();
    const session = await mountSession();
    session.applySnapshot(snapshotFor(SESSION_RECORD, { id: 99, state: 'error' }));
    expect(session.state.status).toBe('running');
    session.applySnapshot(null);
    expect(session.state.status).toBe('running');
});
