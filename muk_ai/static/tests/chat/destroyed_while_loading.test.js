import { Deferred, animationFrame, describe, expect, test } from '@odoo/hoot';
import { Component, useState, xml } from '@odoo/owl';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat } from '@muk_ai/chat/chat';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

describe.current.tags('muk_ai');
defineMailModels();

class Host extends Component {
    static template = xml`<t t-if="state.show"><t t-component="props.child" t-props="props.childProps"/></t>`;
    static props = ['child', 'childProps'];
    setup() {
        this.state = useState({ show: false });
    }
}

function mockBus() {
    const subscribed = new Set();
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe: (name, handler) => subscribed.add(handler),
        unsubscribe: (name, handler) => subscribed.delete(handler),
    });
    return subscribed;
}

function mockChatWindow() {
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        sessionIds: [],
        open() {},
        close() {},
        toggleMinimized() {},
        get activeSessionId() {
            return null;
        },
    });
}

async function destroyWhileHeld(child, childProps, held, subscribed) {
    const host = await mountWithCleanup(Host, { props: { child, childProps } });
    const listeners = subscribed.size;
    host.state.show = true;
    await animationFrame();
    await animationFrame();
    host.state.show = false;
    await animationFrame();
    held.resolve([]);
    await animationFrame();
    expect(subscribed.size).toBe(listeners);
}

test('a chat destroyed before it mounts stops listening to the bus', async () => {
    const subscribed = mockBus();
    mockChatWindow();
    const held = new Deferred();
    onRpc('muk_ai.session', 'search_read', () => [
        { id: 7, name: 'Open', state: 'done', create_date: '2026-04-21 10:00:00' },
    ]);
    onRpc('muk_ai.session', 'get_snapshot', () => held);
    onRpc('muk_ai.session', 'read', () => [{ id: 7, name: 'Open', state: 'done' }]);
    onRpc('muk_ai.agent', 'search_read', () => []);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    onRpc('muk_ai.space', 'fetch_general_domain', () => [['space_id', '=', false]]);
    await destroyWhileHeld(AIChat, { action: { params: {} } }, held, subscribed);
});

test('a systray destroyed before it mounts stops listening to the bus', async () => {
    const subscribed = mockBus();
    mockChatWindow();
    mockService('action', { currentController: null, doAction() {} });
    const held = new Deferred();
    onRpc('muk_ai.session', 'search_read', () => held);
    onRpc('muk_ai.session', 'get_needs_you', () => []);
    onRpc('muk_ai.agent', 'search_read', () => []);
    await destroyWhileHeld(MukAISystray, {}, held, subscribed);
});
