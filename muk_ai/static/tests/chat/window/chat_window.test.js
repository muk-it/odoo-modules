import { describe, expect, test } from '@odoo/hoot';
import {
    mockService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();

const SESSION_RECORD = {
    id: 11,
    name: 'Popout',
    state: 'done',
    events: [],
    oldest_sequence: null,
    has_more_older: false,
    pending_ask: null,
    view_context: null,
    last_text: 'hello',
    error_message: null,
    iteration_count: 1,
    total_input_tokens: 3,
    total_output_tokens: 1,
    last_input_tokens: 1,
    context_window: 8000,
    total_cost: 0.0025,
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

function registerMocks() {
    onRpc('muk_ai.session', 'read', ({ args }) => [
        { ...SESSION_RECORD, id: args[0][0] },
    ]);
    const events = { opened: [], closed: [], actions: [] };
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => {
            events.opened.push(id);
        },
        close: (id) => {
            events.closed.push(id);
        },
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('action', {
        doAction: (a) => {
            events.actions.push(a);
            return Promise.resolve();
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

test('ChatWindow mounts and loads the session through use_ai_session', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    expect(window_.session.state.sessionId).toBe(11);
    expect(window_.session.state.name).toBe('Popout');
});

test('costPill uses formatted cost + USD tooltip', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    const pill = window_.costPill;
    expect(pill.label).toBe('0.0025');
    expect(String(pill.tooltip)).toMatch(/USD/);
});

test('approvalPill reflects session.state.effectiveApprovalMode', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    const pill = window_.approvalPill;
    expect(String(pill.label)).toMatch(/Ask/i);
});

test('onFullscreen closes the popout then dispatches the chat action', async () => {
    const events = registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    await window_.onFullscreen();
    expect(events.closed).toEqual([11]);
    expect(events.actions[0].tag).toBe('muk_ai.chat');
    expect(events.actions[0].params.session_id).toBe(11);
});

test('toggleAskView flips mode for a matching tool block', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    window_.session.state.events = [
        { kind: 'ask_user', call_id: 'c1', text: 'Q?', preview: { kind: 'write' } },
    ];
    window_.toggleAskView('c1');
    expect(window_.windowState.askViews.c1).toBe('technical');
});

test('renderedTurns reads from the session log', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    window_.session.state.events = [
        { kind: 'user_message', content: 'hi', attachments: [] },
        { kind: 'text', content: 'hello there' },
    ];
    const turns = window_.renderedTurns;
    expect(turns.map((t) => t.role)).toEqual(['user', 'assistant']);
});

test('viewContextLabel falls back to empty when no pinned context', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    expect(window_.viewContextLabel).toBe('');
    window_.session.state.viewContext = {
        kind: 'record',
        model: 'res.partner',
        display_name: 'Acme',
    };
    expect(window_.viewContextLabel).toMatch(/Acme/);
});

test('onOpenAttachment opens the file viewer via toFileModel', async () => {
    registerMocks();
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    const opened = [];
    window_.fileViewer.open = (file) => opened.push(file);
    window_.onOpenAttachment({
        id: 5,
        filename: 'p.png',
        mimetype: 'image/png',
        size: 10,
    });
    expect(opened).toHaveLength(1);
    expect(opened[0].id).toBe(5);
});
