import { describe, expect, test } from '@odoo/hoot';
import { resize } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat } from '@muk_ai/chat/chat';

describe.current.tags('muk_ai');
defineMailModels();

const SESSION_RECORD = {
    id: 7,
    name: 'Demo session',
    state: 'done',
    pending_ask: null,
    view_context: null,
    last_text: '',
    error_message: null,
    iteration_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    last_input_tokens: 0,
    context_window: 8000,
    total_cost: 0,
    user_id: false,
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
    pending_user_messages: [],
};

const SNAPSHOT = {
    state: 'done',
    events: [{ event_id: 2, kind: 'user_message', content: 'hi', attachments: [] }],
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
};

function baseMocks({ sessions = [], knownIds = [7] } = {}) {
    onRpc('muk_ai.session', 'search_read', () => sessions);
    onRpc('muk_ai.session', 'read', ({ args }) =>
        knownIds.includes(args[0][0]) ? [{ ...SESSION_RECORD, id: args[0][0] }] : [],
    );
    onRpc('muk_ai.session', 'get_snapshot', () => SNAPSHOT);
    onRpc('muk_ai.agent', 'search_read', () => []);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    const notifications = [];
    mockService('notification', { add: (msg) => notifications.push(String(msg)) });
    return notifications;
}

test('a session requested by the action opens straight away with the sidebar closed', async () => {
    baseMocks({
        sessions: [
            { id: 5, name: 'Other', state: 'done', create_date: '2026-04-20 10:00:00' },
            {
                id: 7,
                name: 'Wanted',
                state: 'done',
                create_date: '2026-04-21 10:00:00',
            },
        ],
    });
    const chat = await mountWithCleanup(AIChat, {
        props: { action: { params: { session_id: '7' } } },
    });
    expect(chat.session.state.sessionId).toBe(7);
    expect(chat.state.sidebarHidden).toBe(true);
    expect(chat.state.loading).toBe(false);
});

test('a requested session missing from the sidebar is loaded directly', async () => {
    baseMocks({ sessions: [], knownIds: [9] });
    const chat = await mountWithCleanup(AIChat, {
        props: { action: { params: { session_id: 9 } } },
    });
    expect(chat.session.state.sessionId).toBe(9);
    expect(chat.state.sidebarHidden).toBe(true);
});

test('a requested session that no longer exists warns and falls back', async () => {
    const notifications = baseMocks({
        sessions: [
            { id: 5, name: 'Other', state: 'done', create_date: '2026-04-20 10:00:00' },
        ],
        knownIds: [5],
    });
    const chat = await mountWithCleanup(AIChat, {
        props: { action: { params: { session_id: 999 } } },
    });
    expect(notifications.some((m) => /no longer exists/.test(m))).toBe(true);
    expect(chat.session.state.sessionId).toBe(5);
    expect(chat.state.sidebarHidden).toBe(false);
});

test('a non-numeric requested session id is ignored', async () => {
    const notifications = baseMocks({
        sessions: [
            { id: 5, name: 'Other', state: 'done', create_date: '2026-04-20 10:00:00' },
        ],
        knownIds: [5],
    });
    const chat = await mountWithCleanup(AIChat, {
        props: { action: { params: { session_id: 'nope' } } },
    });
    expect(notifications).toEqual([]);
    expect(chat.session.state.sessionId).toBe(5);
});

test('on a phone-sized viewport the sidebar starts collapsed', async () => {
    baseMocks({
        sessions: [
            { id: 5, name: 'Other', state: 'done', create_date: '2026-04-20 10:00:00' },
        ],
        knownIds: [5],
    });
    await resize({ width: 500, height: 800 });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    expect(chat.session.state.sessionId).toBe(5);
    expect(chat.state.sidebarHidden).toBe(true);
});

test('a failed session creation reopens the composer instead of freezing it', async () => {
    baseMocks({
        sessions: [
            { id: 7, name: 'Demo', state: 'done', create_date: '2026-04-20 10:00:00' },
        ],
    });
    onRpc('muk_ai.session', 'create', () => {
        throw new Error('quota reached');
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    let raised = null;
    await chat.onNewSession().catch((error) => {
        raised = error;
    });
    expect(raised).not.toBe(null);
    expect(chat.session.state.loading).toBe(false);
    expect(chat.session.state.sessionId).toBe(7);
});

test('forking a turn switches the chat to the new session', async () => {
    baseMocks({
        sessions: [
            { id: 7, name: 'Demo', state: 'done', create_date: '2026-04-20 10:00:00' },
        ],
        knownIds: [7, 42],
    });
    onRpc('muk_ai.session', 'fork_at_event', () => 42);
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    await chat.session.runForkAtEvent(2);
    await animationFrame();
    expect(chat.session.state.sessionId).toBe(42);
});

test('handing a chat over removes it from the sidebar and opens the next one', async () => {
    baseMocks({
        sessions: [
            { id: 7, name: 'Demo', state: 'done', create_date: '2026-04-21 10:00:00' },
            { id: 8, name: 'Next', state: 'done', create_date: '2026-04-20 10:00:00' },
        ],
        knownIds: [7, 8],
    });
    const dialogs = [];
    mockService('dialog', {
        add: (component, props) => {
            dialogs.push(props);
            return () => {};
        },
    });
    onRpc('muk_ai.session', 'action_handover', () => true);
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.openHandoverPicker();
    dialogs[0].onSelected([12]);
    await animationFrame();
    await animationFrame();
    expect(chat.session.state.sessionId).toBe(8);
});
