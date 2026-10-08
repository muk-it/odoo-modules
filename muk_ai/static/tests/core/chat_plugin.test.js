import { animationFrame, expect, mockDate, test } from '@odoo/hoot';
import { getService, onRpc, patchWithCleanup } from '@web/../tests/web_test_helpers';
import { BusPlugin } from '@bus/services/bus_plugin';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import {
    defineAIModels,
    emit,
    getChat,
    openSession,
    recordNotifications,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

test('a chat channel is followed once however many surfaces show it', async () => {
    const chat = await getChat();
    patchWithCleanup(getService(BusPlugin), {
        addChannel: (channel) => expect.step(`add ${channel}`),
        deleteChannel: (channel) => expect.step(`delete ${channel}`),
    });
    const first = chat.acquire(3);
    const second = chat.acquire(3);
    expect(first).toBe(second);
    chat.release(3);
    chat.release(3);
    chat.acquire(3);
    expect.verifySteps([
        'add muk_ai.session_3',
        'delete muk_ai.session_3',
        'add muk_ai.session_3',
    ]);
});

test('a chat keeps its draft between the surfaces showing it', async () => {
    const session = await openSession(1);
    session.state.input = 'half written';
    session.chat.release(1);
    expect((await openSession(1)).state.input).toBe('half written');
});

test('windows open once, minimize, close and pin the view shown to their chat', async () => {
    const chat = await getChat();
    const target = {
        viewType: 'list',
        build: () => ({ kind: 'list', model: 'res.partner', view_type: 'list' }),
    };
    chat.registerTarget(target);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) =>
        expect.step(`pin ${args[0]} ${args[1].model}`),
    );
    chat.openWindow(4);
    chat.openWindow(4);
    chat.openWindow(5);
    chat.toggleWindow(5);
    expect(chat.windows.map((window) => [window.id, window.minimized])).toEqual([
        [4, false],
        [5, true],
    ]);
    chat.openWindow(5);
    chat.closeWindow(4);
    await animationFrame();
    expect(chat.windowIds).toEqual([5]);
    expect.verifySteps(['pin 4 res.partner', 'pin 5 res.partner']);
    chat.pushContext(target.build());
    chat.pushContext(target.build());
    await animationFrame();
    expect.verifySteps(['pin 5 res.partner']);
});

test('state notifications patch the rows, a deletion drops the chat everywhere', async () => {
    const chat = await getChat();
    const seen = [];
    chat.events.addEventListener('session_state', ({ detail }) =>
        seen.push(detail.session_id),
    );
    chat.setRows([{ id: 6, name: 'Old', state: 'done' }]);
    chat.openWindow(6);
    await emit('muk_ai.session_state', {
        session_id: 6,
        name: 'New',
        state: 'running',
    });
    expect(chat.rows[6]).toMatchObject({ name: 'New', state: 'running' });
    await emit('muk_ai.session_state', { session_id: 6, deleted: true });
    expect(chat.rows[6]).toBe(undefined);
    expect(chat.windowIds).toEqual([]);
    expect(seen).toEqual([6, 6]);
});

test('the badge loads once and follows its pushes', async () => {
    onRpc('muk_ai.session', 'notification_badge', () => {
        expect.step('badge');
        return { count: 2, session_ids: [1, 2], space_unread: { 3: 1 } };
    });
    const chat = await getChat();
    await Promise.all([chat.loadBadge(), chat.loadBadge()]);
    expect.verifySteps(['badge']);
    expect(chat.badge).toEqual({ count: 2, unreadIds: [1, 2], spaceUnread: { 3: 1 } });
    await emit('muk_ai.notification_badge', { session_ids: [2], space_unread: {} });
    expect(chat.badge.count).toBe(1);
});

test('a finished chat toasts unless it is on screen or the notice is stale', async () => {
    mockDate('2026-01-01 10:00:00', 0);
    const notes = await recordNotifications();
    onRpc('muk_ai.session', 'dismiss_notifications', ({ args }) =>
        expect.step(`dismiss ${args[0]}`),
    );
    const notice = (sessionId, at, state = 'done') => ({
        session_id: sessionId,
        state,
        title: 'Report ready',
        message: 'All done',
        at,
    });
    await emit('muk_ai.session_notification', notice(2, '2026-01-01 09:59:00'));
    await emit('muk_ai.session_notification', notice(2, '2026-01-01 09:50:00'));
    await emit(
        'muk_ai.session_notification',
        notice(2, '2026-01-01 09:59:30', 'error'),
    );
    expect(notes.map((note) => note.type)).toEqual(['success', 'danger']);
    await openSession(2);
    await emit('muk_ai.session_notification', notice(2, '2026-01-01 09:59:50'));
    expect(notes).toHaveLength(2);
    expect.verifySteps(['dismiss 2', 'dismiss 2']);
});

test('a message of an AI chat opens the AI chat instead of the record', async () => {
    await getChat();
    const thread = getService('mail.store')['mail.thread'].insert({
        model: 'muk_ai.session',
        id: 9,
    });
    expect(thread.openRecordActionRequest).toEqual({
        type: 'ir.actions.client',
        tag: 'muk_ai.chat',
        params: { session_id: 9 },
    });
});

test('a new chat is created, pinned to the view and announced', async () => {
    const chat = await getChat();
    const opened = [];
    patchWithCleanup(getService(ActionPlugin), {
        doAction: (action) => opened.push(action),
    });
    chat.events.addEventListener('created', ({ detail }) =>
        expect.step(`created ${detail.id}`),
    );
    onRpc('muk_ai.session', 'set_view_context', ({ args }) =>
        expect.step(`pin ${args[1].model}`),
    );
    chat.registerTarget({ build: () => ({ kind: 'list', model: 'res.partner' }) });
    const id = await chat.createSession({ name: 'Mine' });
    await chat.openFullChat(id);
    expect.verifySteps(['pin res.partner', `created ${id}`]);
    expect(opened).toEqual([
        { type: 'ir.actions.client', tag: 'muk_ai.chat', params: { session_id: id } },
    ]);
});
