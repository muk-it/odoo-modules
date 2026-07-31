import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import {
    mockService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat } from '@muk_ai/chat/chat';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();

const SESSION_RECORD = {
    id: 7,
    name: 'Demo session',
    state: 'done',
    events: [],
    oldest_sequence: null,
    has_more_older: false,
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
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

const SNAPSHOT_RUNNING = {
    state: 'running',
    events: [],
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
};

function registerMocks({ sessions = [], agents = [] } = {}) {
    onRpc('muk_ai.session', 'search_read', () => sessions);
    onRpc('muk_ai.session', 'read', ({ args }) => [
        { ...SESSION_RECORD, id: args[0][0] },
    ]);
    onRpc('muk_ai.agent', 'search_read', () => agents);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    const events = { opened: [], actions: [] };
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => {
            events.opened.push(id);
        },
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
    mockService('notification', { add: () => {} });
    return events;
}

test('onNewSession keeps the composer closed until the new session is bound', async () => {
    registerMocks({ sessions: [{ id: 5, name: 'One', state: 'done' }] });
    let resolveCreate;
    const createGate = new Promise((resolve) => {
        resolveCreate = () => resolve([99]);
    });
    onRpc('muk_ai.session', 'create', () => createGate);
    onRpc('muk_ai.session', 'get_snapshot', () => ({
        ...SNAPSHOT_RUNNING,
        state: 'new',
    }));
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(5);
    expect(chat.session.state.loading).toBe(false);
    const switching = chat.onNewSession();
    await animationFrame();
    expect(chat.session.state.loading).toBe(true);
    resolveCreate();
    await switching;
    expect(chat.session.state.sessionId).toBe(99);
    expect(chat.session.state.loading).toBe(false);
});

test('AIChat mounts and loads sessions into the sidebar', async () => {
    registerMocks({
        sessions: [
            { id: 1, name: 'Alpha', state: 'done', create_date: '2026-04-20 10:00:00' },
            { id: 2, name: 'Bravo', state: 'done', create_date: '2026-04-21 10:00:00' },
        ],
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    expect(chat.state.sessions.length).toBe(2);
    expect(chat.state.loading).toBe(false);
});

test('AIChat suggestions come from the active agent', async () => {
    registerMocks({
        sessions: [],
        agents: [
            {
                id: 3,
                name: 'Helper',
                description: '',
                suggestions: [
                    { label: 'Plan a trip', prompt: 'plan a trip' },
                    { prompt: '   ' },
                    { label: 'Summarize', prompt: 'summarize this' },
                ],
            },
        ],
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    const list = chat.suggestions;
    expect(list).toHaveLength(2);
    expect(list[0]).toEqual({ label: 'Plan a trip', prompt: 'plan a trip' });
    expect(list[1]).toEqual({ label: 'Summarize', prompt: 'summarize this' });
});

test('onNewSession creates a fresh session and selects it', async () => {
    registerMocks({ sessions: [] });
    onRpc('muk_ai.session', 'create', () => [42]);
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onNewSession();
    expect(chat.session.state.sessionId).toBe(42);
});

test('onNewSession carries over view_context from the previous session', async () => {
    registerMocks({ sessions: [{ id: 5, name: 'One', state: 'done' }] });
    onRpc('muk_ai.session', 'read', ({ args }) => [
        {
            ...SESSION_RECORD,
            id: args[0][0],
            view_context: {
                kind: 'record',
                model: 'res.partner',
                id: 99,
                display_name: 'Acme',
            },
        },
    ]);
    onRpc('muk_ai.session', 'create', () => [101]);
    const seedCalls = [];
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        seedCalls.push(args);
        return {};
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(5);
    await chat.onNewSession();
    expect(chat.session.state.sessionId).toBe(101);
    expect(seedCalls).toHaveLength(1);
    expect(seedCalls[0]).toEqual([
        101,
        { kind: 'record', model: 'res.partner', id: 99, display_name: 'Acme' },
    ]);
});

test('onSelectSession loads the session from the sidebar', async () => {
    registerMocks({
        sessions: [{ id: 5, name: 'One', state: 'done' }],
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(5);
    expect(chat.session.state.sessionId).toBe(5);
});

test('onRenameSession writes new name and updates state for active session', async () => {
    registerMocks({ sessions: [{ id: 5, name: 'Old', state: 'done' }] });
    let written = null;
    onRpc('muk_ai.session', 'write', ({ args }) => {
        written = args;
        return true;
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(5);
    await chat.onRenameSession(5, 'New');
    expect(written).toEqual([[5], { name: 'New' }]);
    expect(chat.session.state.name).toBe('New');
});

test('onDeleteSession unlinks and selects the next session', async () => {
    let unlinked = null;
    registerMocks({
        sessions: [
            { id: 5, name: 'One', state: 'done' },
            { id: 6, name: 'Two', state: 'done' },
        ],
    });
    onRpc('muk_ai.session', 'unlink', ({ args }) => {
        unlinked = args;
        return true;
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(5);
    await chat.onDeleteSession(5);
    expect(unlinked).toEqual([[5]]);
});

test('toggleSidebar flips sidebarHidden', async () => {
    registerMocks({ sessions: [] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    const before = chat.state.sidebarHidden;
    chat.toggleSidebar();
    expect(chat.state.sidebarHidden).toBe(!before);
});

test('onPopout opens a chat window for the active session', async () => {
    const events = registerMocks({ sessions: [{ id: 9, name: 'Pop', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(9);
    chat.onPopout();
    expect(events.opened).toEqual([9]);
});

test('onPopout is a noop when no active session', async () => {
    const events = registerMocks({ sessions: [] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.onPopout();
    expect(events.opened).toEqual([]);
});

test('onSubmitSuggestion starts sending with the suggested prompt', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    let startArgs = null;
    onRpc('muk_ai.session', 'start', ({ args }) => {
        startArgs = args;
        return SNAPSHOT_RUNNING;
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    await chat.onSubmitSuggestion('List installed modules.');
    expect(startArgs).toEqual([7, 'List installed modules.']);
});

test('inputPlaceholder falls back to default when idle', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    expect(String(chat.inputPlaceholder)).toMatch(/Message the assistant/i);
});

test('_refreshSidebar reflects session status back into the sidebar row', async () => {
    registerMocks({
        sessions: [{ id: 7, name: 'Demo', state: 'done' }],
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.status = 'error';
    chat._refreshSidebar();
    expect(chat.state.sessions[0].state).toBe('error');
});

test('_onUserBusEvent updates an existing sidebar row in place', async () => {
    registerMocks({
        sessions: [{ id: 7, name: 'Old', state: 'done' }],
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat._onUserBusEvent({ session_id: 7, state: 'running', name: 'New' });
    expect(chat.state.sessions[0].state).toBe('running');
    expect(chat.state.sessions[0].name).toBe('New');
});

test('_onUserBusEvent for the active session mirrors fields on session state', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat._onUserBusEvent({
        session_id: 7,
        state: 'running',
        iteration_count: 3,
        total_input_tokens: 42,
        total_output_tokens: 17,
        last_input_tokens: 10,
        context_window: 8000,
    });
    expect(chat.session.state.status).toBe('running');
    expect(chat.session.state.iterationCount).toBe(3);
    expect(chat.session.state.inputTokens).toBe(42);
    expect(chat.session.state.outputTokens).toBe(17);
    expect(chat.session.state.lastInputTokens).toBe(10);
    expect(chat.session.state.contextWindow).toBe(8000);
});

test('_onUserBusEvent with empty sidebar leaves state idle', async () => {
    registerMocks();
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.state.sessions = [];
    chat._onUserBusEvent({ session_id: 999, state: 'running' });
    expect(chat.state.sessions).toEqual([]);
});

test('_onUserBusEvent ignores empty payload', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    const before = chat.state.sessions[0].state;
    chat._onUserBusEvent(null);
    chat._onUserBusEvent({});
    expect(chat.state.sessions[0].state).toBe(before);
});

test('isToolHiddenForAsk returns true for pending-approval tool blocks', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.pendingAsk = { kind: 'approval', call_id: 'c42' };
    const turn = { blocks: [{ type: 'tool', callId: 'c42' }] };
    const block = { result: null, callId: 'c42' };
    expect(chat.isToolHiddenForAsk(block, turn)).toBe(true);
});

test('isToolHiddenForAsk returns false when the block has a result', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    const block = { result: 'ok', callId: 'c1' };
    expect(chat.isToolHiddenForAsk(block, { blocks: [] })).toBe(false);
});

test('isToolHiddenForAsk returns true when turn already has an ask block for the same callId', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.pendingAsk = null;
    const block = { result: null, callId: 'c8' };
    const turn = { blocks: [{ type: 'ask', callId: 'c8' }] };
    expect(chat.isToolHiddenForAsk(block, turn)).toBe(true);
});

test('onRemoveAttachment forwards to session.onRemoveAttachment', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    onRpc('muk_ai.session', 'discard_attachments', () => true);
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.pendingAttachments = [{ id: 1, filename: 'a.txt' }];
    await chat.onRemoveAttachment(1);
    expect(chat.session.state.pendingAttachments).toEqual([]);
});

test('onSend dispatches the session send flow and refreshes sidebar', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    let started = false;
    onRpc('muk_ai.session', 'start', () => {
        started = true;
        return {
            state: 'running',
            events: [],
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
        };
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.input = 'hello';
    await chat.onSend();
    expect(started).toBe(true);
});

test('onStop dispatches session stop flow', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    let stopped = false;
    onRpc('muk_ai.session', 'action_stop', () => {
        stopped = true;
        return {
            state: 'stopped',
            events: [],
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
        };
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    await chat.onStop();
    expect(stopped).toBe(true);
});

test('onAttachFiles forwards to session.onAttachFiles', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    let uploaded = null;
    onRpc('muk_ai.session', 'upload_attachments', ({ args }) => {
        uploaded = args[1];
        return [{ id: 101, filename: 'p.png', mimetype: 'image/png' }];
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    await chat.onAttachFiles([new File(['x'], 'p.png', { type: 'image/png' })]);
    expect(uploaded).toHaveLength(1);
    expect(uploaded[0].filename).toBe('p.png');
});

test('onStartWithPrompt creates a session then sends the prompt', async () => {
    registerMocks({ sessions: [] });
    let startedWith = null;
    const createdId = 42;
    onRpc('muk_ai.session', 'create', () => [createdId]);
    onRpc('muk_ai.session', 'start', ({ args }) => {
        startedWith = args;
        return {
            state: 'running',
            events: [],
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
        };
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onStartWithPrompt('Say hello');
    expect(startedWith).toEqual([42, 'Say hello']);
});

test('onOpenAttachment opens via the file viewer', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    const opened = [];
    chat.fileViewer.open = (file) => opened.push(file);
    await chat.onSelectSession(7);
    chat.onOpenAttachment({
        id: 5,
        filename: 'p.png',
        mimetype: 'image/png',
        size: 10,
    });
    expect(opened).toHaveLength(1);
    expect(opened[0].id).toBe(5);
});

test('contextPercent returns an integer ratio of last/context window', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.lastInputTokens = 2000;
    chat.session.state.contextWindow = 8000;
    expect(chat.contextPercent).toBe(25);
});

test('contextPercent is 0 when lastInputTokens is 0', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.lastInputTokens = 0;
    expect(chat.contextPercent).toBe(0);
});

test('isToolStreaming is true for null-result blocks while running', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.status = 'running';
    expect(chat.isToolStreaming({ result: null, callId: 'c1' })).toBe(true);
    expect(chat.isToolStreaming({ result: undefined, callId: 'c2' })).toBe(true);
});

test('isToolStreaming is false once a result lands', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.status = 'running';
    expect(chat.isToolStreaming({ result: '[]', callId: 'c3' })).toBe(false);
    expect(chat.isToolStreaming({ result: { error: 'x' }, callId: 'c4' })).toBe(false);
});

test('isToolStreaming is false when status is not running', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.status = 'done';
    expect(chat.isToolStreaming({ result: null, callId: 'c5' })).toBe(false);
    chat.session.state.status = 'waiting';
    expect(chat.isToolStreaming({ result: null, callId: 'c6' })).toBe(false);
});

test('isToolStreaming is true while compacting', async () => {
    registerMocks({ sessions: [{ id: 7, name: 'Demo', state: 'done' }] });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    chat.session.state.status = 'compacting';
    expect(chat.isToolStreaming({ result: null, callId: 'c7' })).toBe(true);
});
