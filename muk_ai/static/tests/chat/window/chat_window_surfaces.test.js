import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
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

const EVENTS = [
    { event_id: 1, kind: 'user_message', content: 'clean it up', attachments: [] },
    {
        event_id: 2,
        kind: 'tool_call',
        call_id: 'c1',
        name: 'unlink',
        arguments: '{"ids": [1]}',
    },
    { event_id: 3, kind: 'text', content: 'Awaiting your approval.' },
];

const SESSION_RECORD = {
    id: 11,
    name: 'Popout',
    state: 'done',
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
    user_id: false,
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
    pending_user_messages: [],
};

function registerMocks(record = {}) {
    onRpc('muk_ai.session', 'read', ({ args }) => [
        { ...SESSION_RECORD, ...record, id: args[0][0] },
    ]);
    onRpc('muk_ai.session', 'get_snapshot', () => ({
        id: 11,
        state: SESSION_RECORD.state,
        events: EVENTS,
        oldest_sequence: null,
        has_more_older: false,
        pending_ask: null,
        view_context: null,
        error_message: null,
        iteration_count: 1,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_cost: 0,
        last_input_tokens: 0,
        context_window: 8000,
        override_approval_mode: false,
        effective_approval_mode: 'ask',
        pending_user_messages: [],
        ...record,
    }));
    onRpc('muk_ai.agent', 'search_read', () => []);
    const events = { opened: [], closed: [] };
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => events.opened.push(id),
        close: (id) => events.closed.push(id),
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

function pasteFiles(target, files) {
    const data = new DataTransfer();
    for (const file of files) {
        data.items.add(file);
    }
    const event = new ClipboardEvent('paste', {
        clipboardData: data,
        bubbles: true,
        cancelable: true,
    });
    target.dispatchEvent(event);
    return event;
}

async function mountWindow({ minimized = false, record = {} } = {}) {
    const events = registerMocks(record);
    const closed = [];
    const win = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId: 11,
            minimized,
            onClose: () => closed.push(11),
            onToggleMinimized: () => {},
        },
    });
    await animationFrame();
    return { win, events, closed };
}

test('pasting a file into the window uploads it as an attachment', async () => {
    const { win } = await mountWindow();
    let uploaded = null;
    onRpc('muk_ai.session', 'upload_attachments', ({ args }) => {
        uploaded = args[1];
        return [{ id: 71, filename: 'note.txt', mimetype: 'text/plain' }];
    });
    const event = pasteFiles(document.body, [
        new File(['x'], 'note.txt', { type: 'text/plain' }),
    ]);
    await animationFrame();
    expect(event.defaultPrevented).toBe(true);
    expect(uploaded[0].filename).toBe('note.txt');
    expect(win.session.state.pendingAttachments).toHaveLength(1);
});

test('a minimized window ignores pasted files', async () => {
    const { win } = await mountWindow({ minimized: true });
    let calls = 0;
    onRpc('muk_ai.session', 'upload_attachments', () => {
        calls++;
        return [];
    });
    pasteFiles(document.body, [new File(['x'], 'note.txt', { type: 'text/plain' })]);
    await animationFrame();
    expect(calls).toBe(0);
    expect(win.session.state.pendingAttachments).toEqual([]);
});

test('a paste with no file attached is ignored', async () => {
    const { win } = await mountWindow();
    let calls = 0;
    onRpc('muk_ai.session', 'upload_attachments', () => {
        calls++;
        return [];
    });
    const data = new DataTransfer();
    data.setData('text/plain', 'nope');
    document.body.dispatchEvent(
        new ClipboardEvent('paste', {
            clipboardData: data,
            bubbles: true,
            cancelable: true,
        }),
    );
    await animationFrame();
    expect(calls).toBe(0);
    expect(win.session.state.pendingAttachments).toEqual([]);
});

test('the sources panel of each turn expands on its own', async () => {
    const { win } = await mountWindow();
    const turn = { eventId: 3 };
    expect(win.isTurnSourcesExpanded(turn, 0)).toBe(false);
    win.toggleTurnSources(turn, 0);
    expect(win.isTurnSourcesExpanded(turn, 0)).toBe(true);
    expect(win.isTurnSourcesExpanded({}, 1)).toBe(false);
    win.toggleTurnSources(turn, 0);
    expect(win.isTurnSourcesExpanded(turn, 0)).toBe(false);
});

test('a tool awaiting approval is hidden and shown again once it resolves', async () => {
    const { win } = await mountWindow();
    win.session.state.pendingAsk = { kind: 'approval', call_id: 'c1' };
    const turn = { blocks: [{ type: 'tool', callId: 'c1' }] };
    expect(win.isToolHiddenForAsk({ callId: 'c1', result: null }, turn)).toBe(true);
    expect(win.isToolHiddenForAsk({ callId: 'c1', result: 'ok' }, turn)).toBe(false);
    win.session.state.pendingAsk = null;
    expect(win.isToolHiddenForAsk({ callId: 'c1', result: null }, turn)).toBe(false);
    const askTurn = { blocks: [{ type: 'ask', callId: 'c1' }] };
    expect(win.isToolHiddenForAsk({ callId: 'c1', result: null }, askTurn)).toBe(true);
});

test('a pending tool only shows the streaming state while the turn runs', async () => {
    const { win } = await mountWindow();
    win.session.state.status = 'running';
    expect(win.isToolStreaming({ callId: 'c1', result: null })).toBe(true);
    expect(win.isToolStreaming({ callId: 'c1', result: '[]' })).toBe(false);
    win.session.state.status = 'compacting';
    expect(win.isToolStreaming({ callId: 'c1', result: null })).toBe(true);
    win.session.state.status = 'done';
    expect(win.isToolStreaming({ callId: 'c1', result: null })).toBe(false);
});

test('expanding a tool card in the window is remembered per call', async () => {
    const { win } = await mountWindow();
    expect(win.isToolExpanded('c1')).toBe(false);
    win.toggleToolBlock('c1');
    expect(win.isToolExpanded('c1')).toBe(true);
    expect(win.isToolExpanded('c2')).toBe(false);
});

test('forking from the window opens a second window on the new session', async () => {
    const { win, events } = await mountWindow();
    onRpc('muk_ai.session', 'fork_at_event', () => 77);
    await win.session.runForkAtEvent(1);
    expect(events.opened).toEqual([77]);
});

test('handing the window session over closes the window', async () => {
    const { win, closed } = await mountWindow();
    const dialogs = [];
    mockService('dialog', {
        add: (component, props) => {
            dialogs.push(props);
            return () => {};
        },
    });
    onRpc('muk_ai.session', 'action_handover', () => true);
    win.session.openHandoverPicker();
    dialogs[0].onSelected([12]);
    await animationFrame();
    expect(closed).toEqual([11]);
});
