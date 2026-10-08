import { animationFrame, expect, test } from '@odoo/hoot';
import {
    contains,
    getService,
    mountWebClient,
    onRpc,
} from '@web/../tests/web_test_helpers';

import { dockWidth } from '@muk_ai/chat/dock/dock';
import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { defineAIModels, snapshot } from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const history = [
    { kind: 'user_message', content: 'Hello', event_id: 1, sequence: 1 },
    { kind: 'text', content: 'Hi', event_id: 2, sequence: 2 },
];

async function openWindow(id = 1) {
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    chat.openWindow(id);
    await animationFrame();
    return chat;
}

test('a chat opens in one window that minimizes from its header and closes', async () => {
    const chat = await openWindow(1);
    chat.openWindow(1);
    await animationFrame();
    expect('.mk_window').toHaveCount(1);
    expect('.mk_window_title').toHaveText('Demo');
    expect('.mk_window .mk_conversation_compact').toHaveCount(1);
    await contains('.mk_window_header').click();
    expect('.mk_window.mk_window_min .mk_conversation').toHaveCount(0);
    await contains('.mk_window_btn[title=Expand]').click();
    expect('.mk_window:not(.mk_window_min) .mk_conversation').toHaveCount(1);
    await contains('.mk_window_btn[title=Close]').click();
    expect('.mk_window').toHaveCount(0);
});

test.tags('desktop');
test('fullscreen moves the chat from its window to the page, keeping the draft and the pin', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => ({
        ...snapshot(),
        view_context: { kind: 'list', model: 'res.partner', view_type: 'kanban' },
    }));
    await openWindow(1);
    expect('.mk_window .mk_conversation > .mk_ctx_chip').toHaveCount(1);
    expect('.mk_window_subheader .mk_ctx_chip').toHaveCount(0);
    await contains('.mk_window textarea').edit('half written', { confirm: false });
    await contains('.mk_window_btn[title="Open fullscreen"]').click();
    await animationFrame();
    expect('.mk_window').toHaveCount(0);
    expect('.mk_chat .mk_main_title').toHaveText('Demo');
    expect('.mk_chat .mk_composer textarea').toHaveValue('half written');
    expect('.mk_main_header .mk_ctx_chip').toHaveCount(1);
    expect('.mk_conversation > .mk_ctx_chip').toHaveCount(0);
});

test('a branch made in a window opens in a window of its own', async () => {
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshot({ id: args[0], events: history }),
    );
    onRpc('muk_ai.session', 'fork_at_event', () => 2);
    const chat = await openWindow(1);
    await contains('.mk_window .mk_turn_assistant .mk_msg_fork', {
        visible: false,
    }).click();
    await animationFrame();
    expect(chat.windowIds).toEqual([1, 2]);
    expect('.mk_window').toHaveCount(2);
});

test.tags('desktop');
test('the dock grows with its windows and leaves Discuss fewer chat windows meanwhile', async () => {
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    const hub = getService('mail.store').chatHub;
    const free = hub.maxOpened;
    chat.openWindow(1);
    chat.openWindow(2);
    await animationFrame();
    expect('.mk_window_dock').toHaveAttribute(
        'style',
        new RegExp(`--mk-dock-width: ${dockWidth(2)}px`),
    );
    expect(hub.maxOpened).toBeLessThan(free);
    chat.closeWindow(1);
    chat.closeWindow(2);
    await animationFrame();
    expect('.mk_window_dock').toHaveAttribute('style', /--mk-dock-width: 0px/);
    expect(hub.maxOpened).toBe(free);
});
