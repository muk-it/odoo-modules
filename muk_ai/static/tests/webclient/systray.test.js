import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll } from '@odoo/hoot-dom';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

describe.current.tags('muk_ai');
defineMailModels();


function makeChatWindowService() {
    const events = { opened: [] };
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => { events.opened.push(id); },
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() { return null; },
    });
    return events;
}


function makeBusMock() {
    const handlers = new Map();
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe(name, cb) { handlers.set(name, cb); },
        unsubscribe(name) { handlers.delete(name); },
    });
    return {
        emit(name, payload) {
            const cb = handlers.get(name);
            if (cb) cb(payload);
        },
    };
}


test('systray loads sessions and exposes runningCount for 2 of 3 sessions', async () => {
    onRpc('muk_ai.session', 'search_read', () => [
        { id: 1, name: 'Chat A', state: 'running' },
        { id: 2, name: 'Chat B', state: 'done' },
        { id: 3, name: 'Chat C', state: 'waiting' },
    ]);
    makeBusMock();
    makeChatWindowService();
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    expect(systray.runningCount).toBe(2);
    expect(systray.hasRunning).toBe(true);
});


test('systray handles RPC failure by showing empty list', async () => {
    onRpc('muk_ai.session', 'search_read', () => { throw new Error('down'); });
    makeBusMock();
    makeChatWindowService();
    await mountWithCleanup(MukAISystray, { props: {} });
    expect(document.querySelector('.o-dropdown')).not.toBe(null);
});


test('systray bus event updates a known session row in place', async () => {
    onRpc('muk_ai.session', 'search_read', () => [
        { id: 1, name: 'Chat A', state: 'done' },
    ]);
    const bus = makeBusMock();
    makeChatWindowService();
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    bus.emit('muk_ai.session_state', { session_id: 1, state: 'running', name: 'Renamed' });
    expect(systray.state.sessions[0].state).toBe('running');
    expect(systray.state.sessions[0].name).toBe('Renamed');
});


test('systray bus event for unknown session triggers reload', async () => {
    let loadCount = 0;
    onRpc('muk_ai.session', 'search_read', () => { loadCount++; return []; });
    const bus = makeBusMock();
    makeChatWindowService();
    await mountWithCleanup(MukAISystray, { props: {} });
    const before = loadCount;
    bus.emit('muk_ai.session_state', { session_id: 99, state: 'running' });
    await new Promise((r) => setTimeout(r, 10));
    expect(loadCount).toBe(before + 1);
});


test('statusDotClass maps states to CSS classes', async () => {
    onRpc('muk_ai.session', 'search_read', () => []);
    makeBusMock();
    makeChatWindowService();
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    expect(systray.statusDotClass('running')).toBe('mk_state_running');
    expect(systray.statusDotClass('waiting')).toBe('mk_state_waiting');
    expect(systray.statusDotClass('done')).toBe('mk_state_done');
    expect(systray.statusDotClass('unknown')).toBe('mk_state_new');
});


test('onNewChat creates a session and opens it via chat_window service', async () => {
    let nextId = 100;
    const seen = [];
    onRpc('muk_ai.session', 'search_read', () => []);
    onRpc('muk_ai.session', 'create', ({ args }) => {
        seen.push(args[0]);
        return [++nextId];
    });
    makeBusMock();
    const events = makeChatWindowService();
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    await systray.onNewChat();
    expect(events.opened).toEqual([101]);
    expect(seen[0][0].name).toMatch(/Chat /);
});


test('onOpenSession forwards to chat_window.open', async () => {
    onRpc('muk_ai.session', 'search_read', () => []);
    makeBusMock();
    const events = makeChatWindowService();
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    systray.onOpenSession({ id: 77 });
    expect(events.opened).toEqual([77]);
});


test('onOpenFullChat dispatches the chat action', async () => {
    onRpc('muk_ai.session', 'search_read', () => []);
    makeBusMock();
    makeChatWindowService();
    const actions = [];
    mockService('action', { doAction: (a) => { actions.push(a); return Promise.resolve(); } });
    const systray = await mountWithCleanup(MukAISystray, { props: {} });
    await systray.onOpenFullChat();
    expect(actions[0].tag).toBe('muk_ai.chat');
});
