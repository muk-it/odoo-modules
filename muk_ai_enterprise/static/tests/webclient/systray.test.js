import { describe, expect, test } from '@odoo/hoot';
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { registry } from '@web/core/registry';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import '@muk_ai_enterprise/webclient/systray/systray';

describe.current.tags('muk_ai_enterprise');
defineMailModels();

function makeChatWindowService() {
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
}

function makeBusMock() {
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
}

function makeLauncherMock() {
    const calls = [];
    mockService('aiChatLauncher', {
        launchAIChat: (opts) => {
            calls.push(opts);
            return Promise.resolve();
        },
    });
    return calls;
}

function stubLoads() {
    onRpc('muk_ai.session', 'search_read', () => []);
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 0,
        session_ids: [],
    }));
}

test('the standalone Enterprise AI systray action is removed', async () => {
    expect(registry.category('systray').contains('ai.systray_action')).toBe(false);
});

test('Open Odoo AI launches the Enterprise chat from the systray', async () => {
    stubLoads();
    makeBusMock();
    makeChatWindowService();
    const calls = makeLauncherMock();
    mockService('action', {
        currentController: null,
        doAction: () => Promise.resolve(),
    });
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    systray.onOpenOdooAI();
    expect(calls).toEqual([{ callerComponentName: 'systray_ai_button' }]);
});

test('Open Odoo AI on a form view defers to the chatter bus instead', async () => {
    stubLoads();
    makeBusMock();
    makeChatWindowService();
    const calls = makeLauncherMock();
    mockService('action', {
        currentController: { view: { type: 'form' } },
        doAction: () => Promise.resolve(),
    });
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    const events = [];
    systray.env.bus.addEventListener('AI:OPEN_AI_CHAT', (ev) => events.push(ev.detail));
    systray.onOpenOdooAI();
    expect(events).toEqual([{ origin: 'chatter_ai_button' }]);
    expect(calls).toEqual([]);
});

test('the Open Odoo AI dropdown item is rendered when the menu opens', async () => {
    stubLoads();
    makeBusMock();
    makeChatWindowService();
    makeLauncherMock();
    mockService('action', {
        currentController: null,
        doAction: () => Promise.resolve(),
    });
    await mountWithCleanup(MukAISystray, { props: {} });
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_odoo_ai_icon');
});
