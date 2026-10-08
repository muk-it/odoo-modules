import {
    advanceTime,
    animationFrame,
    expect,
    press,
    queryAllTexts,
    test,
} from '@odoo/hoot';
import {
    contains,
    getService,
    mountWebClient,
    MockServer,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    AISessionModel,
    defineAIModels,
    emit,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

function seedChats() {
    AISessionModel._records = [
        {
            id: 1,
            name: 'Unread report',
            state: 'done',
            notification_unread: true,
            write_date: '2026-01-01 10:00:00',
        },
        {
            id: 2,
            name: 'Busy chat',
            state: 'running',
            write_date: '2026-01-02 10:00:00',
        },
        {
            id: 3,
            name: 'Of a colleague',
            state: 'done',
            user_id: serverState.publicUserId,
        },
    ];
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 1,
        session_ids: [1],
        space_unread: {},
    }));
}

test('the menu lists the unread chats first, then the recent ones, under the badge and the running mark', async () => {
    seedChats();
    await mountWebClient();
    expect('.mk_systray_btn .o_badge').toHaveText('1');
    expect('.mk_systray_btn .mk_systray_running').toHaveCount(1);
    await contains('.mk_systray_btn').click();
    expect(
        queryAllTexts('.mk_systray_menu .mk_systray_item', { inline: true }),
    ).toEqual([
        'New Chat Alt+Shift+B',
        'Open Full Chat Alt+Shift+F',
        'Unread report',
        'Busy chat',
    ]);
    expect('.mk_systray_unread').toHaveText('Unread report');
    expect('.mk_systray_menu').toHaveText(/1 running/);
});

test('the badge follows the bus and caps at 99', async () => {
    await mountWebClient();
    for (const [count, badge] of [
        [5, '5'],
        [120, '99+'],
    ]) {
        await emit('muk_ai.notification_badge', { count, session_ids: [] });
        expect('.mk_systray_btn .o_badge').toHaveText(badge);
    }
    await emit('muk_ai.notification_badge', { count: 0, session_ids: [] });
    expect('.mk_systray_btn .o_badge').toHaveCount(0);
});

test('New Chat and a listed chat open in a window, Open Full Chat opens the page', async () => {
    seedChats();
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_item:contains(Busy chat)').click();
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_item:contains(New Chat)').click();
    expect(chat.windowIds).toEqual([2, 4]);
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_item:contains(Open Full Chat)').click();
    await animationFrame();
    expect('.o_action_manager .mk_chat').toHaveCount(1);
});

test('the hotkeys start a chat in a window and open the full page', async () => {
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    await press(['alt', 'shift', 'b']);
    await animationFrame();
    expect(chat.windowIds).toEqual([3]);
    await press(['alt', 'shift', 'f']);
    await animationFrame();
    expect('.o_action_manager .mk_chat').toHaveCount(1);
});

test('the list picks up chats created or deleted elsewhere', async () => {
    AISessionModel._records = [];
    await mountWebClient();
    await contains('.mk_systray_btn').click();
    expect('.mk_systray_menu').toHaveText(/No chats yet\./);
    const [id] = MockServer.env['muk_ai.session'].create([
        { name: 'From a cron', state: 'done' },
    ]);
    await emit('muk_ai.session_state', { session_id: id, state: 'done' });
    await advanceTime(500);
    await animationFrame();
    expect(queryAllTexts('.mk_systray_menu .mk_systray_item').at(-1)).toBe(
        'From a cron',
    );
    await emit('muk_ai.session_state', { session_id: id, deleted: true });
    expect('.mk_systray_menu').toHaveText(/No chats yet\./);
});
