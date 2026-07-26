import { describe, expect, mockUserAgent, test } from '@odoo/hoot';
import { press, queryOne, waitFor } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
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

test('the alt+shift+r hotkey launches the Enterprise chat', async () => {
    stubLoads();
    makeBusMock();
    makeChatWindowService();
    const calls = makeLauncherMock();
    mockService('action', {
        currentController: null,
        doAction: () => Promise.resolve(),
    });
    await mountWithCleanup(MukAISystray, { props: {} });
    await animationFrame();
    await press(['alt', 'shift', 'r']);
    await animationFrame();
    expect(calls).toEqual([{ callerComponentName: 'systray_ai_button' }]);
});

test('the Odoo AI hotkey label follows the platform', async () => {
    stubLoads();
    makeBusMock();
    makeChatWindowService();
    makeLauncherMock();
    mockService('action', {
        currentController: null,
        doAction: () => Promise.resolve(),
    });
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    expect(systray.odooAIHotkeyLabel).toBe('Alt+Shift+R');
    mockUserAgent('mac');
    expect(systray.odooAIHotkeyLabel).toBe('Ctrl+Shift+R');
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
    const item = await waitFor('.mk_systray_action:has(.mk_systray_odoo_ai_icon)');
    expect(item).toHaveText(/Open Odoo AI/);
    expect(queryOne('.mk_systray_odoo_ai_icon')).toHaveAttribute('alt', 'Odoo AI');
    expect(item.querySelector('.mk_systray_hotkey').textContent).toBe('Alt+Shift+R');
});
