import { describe, expect, test } from '@odoo/hoot';
import { click, queryFirst, resize, waitUntil } from '@odoo/hoot-dom';
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

function snapshotWith(events) {
    return {
        state: 'done',
        events,
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
    };
}

function baseMocks({ events = [], record = {} } = {}) {
    onRpc('muk_ai.session', 'search_read', () => [
        { id: 7, name: 'Demo', state: 'done', create_date: '2026-04-20 10:00:00' },
    ]);
    onRpc('muk_ai.session', 'read', ({ args }) => [
        { ...SESSION_RECORD, ...record, id: args[0][0] },
    ]);
    onRpc('muk_ai.session', 'get_snapshot', () => snapshotWith(events));
    onRpc('muk_ai.agent', 'search_read', () => []);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    const opened = [];
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => opened.push(id),
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
    return opened;
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

function pngFile(name) {
    return new File(['fake-bytes'], name, { type: 'image/png' });
}

async function mountChat(options) {
    const opened = baseMocks(options);
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(7);
    await animationFrame();
    return { chat, opened };
}

test('clicking an image rendered by markdown opens it in the file viewer', async () => {
    const { chat } = await mountChat({
        events: [
            {
                event_id: 2,
                kind: 'text',
                content: '![shot](data:image/png;base64,iVBORw0KGgo=)',
            },
        ],
    });
    const viewed = [];
    chat.fileViewer.open = (file) => viewed.push(file);
    const img = queryFirst('img.mk_md_image');
    expect(img).not.toBe(null);
    await click(img);
    expect(viewed).toHaveLength(1);
    expect(viewed[0].defaultSource).toBe('data:image/png;base64,iVBORw0KGgo=');
});

test('clicking chat text does not open the file viewer', async () => {
    const { chat } = await mountChat({
        events: [{ event_id: 2, kind: 'text', content: 'plain answer' }],
    });
    const viewed = [];
    chat.fileViewer.open = (file) => viewed.push(file);
    await click('.mk_bubble_body');
    expect(viewed).toEqual([]);
});

test('pasting files anywhere in the chat uploads them as attachments', async () => {
    const { chat } = await mountChat();
    let uploaded = null;
    onRpc('muk_ai.session', 'upload_attachments', ({ args }) => {
        uploaded = args[1];
        return [{ id: 33, filename: 'shot.png', mimetype: 'image/png' }];
    });
    const event = pasteFiles(document.body, [pngFile('shot.png')]);
    await animationFrame();
    expect(event.defaultPrevented).toBe(true);
    expect(uploaded).toHaveLength(1);
    expect(uploaded[0].filename).toBe('shot.png');
    expect(chat.session.state.pendingAttachments).toHaveLength(1);
});

test('a paste carrying no file is left alone', async () => {
    const { chat } = await mountChat();
    let calls = 0;
    onRpc('muk_ai.session', 'upload_attachments', () => {
        calls++;
        return [];
    });
    const data = new DataTransfer();
    data.setData('text/plain', 'just text');
    const event = new ClipboardEvent('paste', {
        clipboardData: data,
        bubbles: true,
        cancelable: true,
    });
    document.body.dispatchEvent(event);
    await animationFrame();
    expect(event.defaultPrevented).toBe(false);
    expect(calls).toBe(0);
    expect(chat.session.state.pendingAttachments).toEqual([]);
});

test('pasting while the assistant is running is refused', async () => {
    const { chat } = await mountChat();
    let calls = 0;
    onRpc('muk_ai.session', 'upload_attachments', () => {
        calls++;
        return [];
    });
    chat.session.state.status = 'running';
    pasteFiles(document.body, [pngFile('shot.png')]);
    await animationFrame();
    expect(calls).toBe(0);
});

test('pasting into the composer attaches the file exactly once', async () => {
    const { chat } = await mountChat();
    let calls = 0;
    onRpc('muk_ai.session', 'upload_attachments', () => {
        calls++;
        return [{ id: 33 + calls, filename: 'shot.png', mimetype: 'image/png' }];
    });
    const textarea = queryFirst('.mk_composer textarea');
    expect(textarea).not.toBe(null);
    pasteFiles(textarea, [pngFile('shot.png')]);
    await waitUntil(() => calls > 0);
    await animationFrame();
    expect(calls).toBe(1);
    expect(chat.session.state.pendingAttachments).toHaveLength(1);
});

test('the artifacts panel toggles open and closed', async () => {
    const { chat } = await mountChat();
    expect(chat.state.artifactsHidden).toBe(true);
    chat.toggleArtifacts();
    await animationFrame();
    expect(chat.state.artifactsHidden).toBe(false);
    chat.closeArtifacts();
    await animationFrame();
    expect(chat.state.artifactsHidden).toBe(true);
});

test('opening the artifacts panel on a narrow screen folds the sidebar away', async () => {
    const { chat } = await mountChat();
    await resize({ width: 1000, height: 800 });
    chat.state.sidebarHidden = false;
    chat.toggleArtifacts();
    await animationFrame();
    expect(chat.state.artifactsHidden).toBe(false);
    expect(chat.state.sidebarHidden).toBe(true);
});

test('turn sources expand independently per turn', async () => {
    const { chat } = await mountChat();
    const turn = { eventId: 12 };
    expect(chat.isTurnSourcesExpanded(turn, 0)).toBe(false);
    chat.toggleTurnSources(turn, 0);
    expect(chat.isTurnSourcesExpanded(turn, 0)).toBe(true);
    expect(chat.isTurnSourcesExpanded({}, 1)).toBe(false);
    chat.toggleTurnSources(turn, 0);
    expect(chat.isTurnSourcesExpanded(turn, 0)).toBe(false);
});

test('an ask block switches between the human and technical view', async () => {
    const { chat } = await mountChat({
        events: [
            {
                event_id: 3,
                kind: 'ask_user',
                call_id: 'c9',
                text: 'Delete it?',
                preview: { kind: 'unlink', arguments: { ids: [1] } },
            },
        ],
    });
    const block = chat.renderedTurns
        .flatMap((t) => t.blocks || [])
        .find((b) => b.callId === 'c9');
    expect(block).not.toBe(undefined);
    expect(chat.askViewMode(block)).toBe('human');
    chat.toggleAskView('c9');
    expect(chat.askViewMode(block)).toBe('technical');
    expect(chat.askArgsText(block)).toMatch(/"ids"/);
    chat.toggleAskView('c9');
    expect(chat.askViewMode(block)).toBe('human');
    chat.toggleAskView(null);
    expect(chat.state.askViews.c9).toBe('human');
});

test('a session owned by somebody else is read only', async () => {
    const { chat } = await mountChat({ record: { user_id: [4242, 'Someone'] } });
    expect(chat.isOwner).toBe(false);
    expect(chat.canSend).toBe(false);
    expect(chat.canAttach).toBe(false);
    expect(chat.canStop).toBe(false);
    expect(chat.composerDisabled).toBe(true);
    expect(String(chat.inputPlaceholder)).toMatch(/Read only/);
});

test('popping out on a small screen opens the full-page action instead', async () => {
    const { chat, opened } = await mountChat();
    const actions = [];
    chat.ui = { isSmall: true };
    chat.action = { doAction: (action, options) => actions.push([action, options]) };
    chat.onPopout();
    expect(opened).toEqual([]);
    expect(actions).toHaveLength(1);
    expect(actions[0][0]).toBe('muk_ai.action_ai_chat');
    expect(actions[0][1].additionalContext).toEqual({ default_session_id: 7 });
});

test('the context gauge colours by fill ratio', async () => {
    const { chat } = await mountChat();
    chat.session.state.contextWindow = 8000;
    chat.session.state.lastInputTokens = 1000;
    expect(chat.contextClass).toBe('mk_context_green');
    chat.session.state.lastInputTokens = 6000;
    expect(chat.contextPercent).toBe(75);
    expect(chat.contextClass).toBe('mk_context_amber');
    chat.session.state.lastInputTokens = 7600;
    expect(chat.contextClass).toBe('mk_context_red');
    chat.session.state.contextWindow = 0;
    expect(chat.contextPercent).toBe(0);
    expect(String(chat.contextTooltip)).toMatch(/Context window/);
});

test('the resume countdown is empty until a resume time is known', async () => {
    const { chat } = await mountChat();
    expect(chat.resumeRelativeText).toBe('');
    chat.session.state.resumeAt = new Date(Date.now() + 120000).toISOString();
    expect(String(chat.resumeRelativeText)).toMatch(/resumes in/);
});
