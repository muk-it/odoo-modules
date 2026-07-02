import { describe, expect, test } from '@odoo/hoot';

import { chatWindowService } from '@muk_ai/chat/window/chat_window_service';

describe.current.tags('muk_ai');

function makeEnv({ currentController = null, calls } = {}) {
    const env = {
        services: {
            action: { currentController },
            bus_service: { subscribe: () => {} },
            orm: {
                call: (...args) => {
                    calls.push(['call', ...args]);
                    return Promise.resolve({});
                },
                read: (...args) => {
                    calls.push(['read', ...args]);
                    return Promise.resolve([]);
                },
            },
        },
    };
    return env;
}

test('open registers a window for an unseen session id', () => {
    const calls = [];
    const env = makeEnv({ calls });
    const api = chatWindowService.start(env);
    api.open(5);
    expect(api.state.windows).toHaveLength(1);
    expect(api.state.windows[0]).toEqual({ sessionId: 5, minimized: false });
});

test('open un-minimizes an existing window instead of duplicating', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(7);
    api.toggleMinimized(7);
    expect(api.state.windows[0].minimized).toBe(true);
    api.open(7);
    expect(api.state.windows).toHaveLength(1);
    expect(api.state.windows[0].minimized).toBe(false);
});

test('close removes the window by session id', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(1);
    api.open(2);
    api.close(1);
    expect(api.state.windows.map((w) => w.sessionId)).toEqual([2]);
});

test('close is a noop for unknown session id', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(1);
    api.close(999);
    expect(api.state.windows).toHaveLength(1);
});

test('toggleMinimized flips the minimized flag', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(3);
    expect(api.state.windows[0].minimized).toBe(false);
    api.toggleMinimized(3);
    expect(api.state.windows[0].minimized).toBe(true);
    api.toggleMinimized(3);
    expect(api.state.windows[0].minimized).toBe(false);
});

test('toggleMinimized is a noop for unknown session id', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(1);
    api.toggleMinimized(99);
    expect(api.state.windows[0].minimized).toBe(false);
});

test('activeSessionId picks the last non-minimized window', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(10);
    api.open(20);
    api.open(30);
    expect(api.activeSessionId).toBe(30);
    api.toggleMinimized(30);
    expect(api.activeSessionId).toBe(20);
});

test('activeSessionId falls back to first window when all minimized', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(10);
    api.open(20);
    api.toggleMinimized(10);
    api.toggleMinimized(20);
    expect(api.activeSessionId).toBe(10);
});

test('activeSessionId is null when no windows', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    expect(api.activeSessionId).toBe(null);
});

test('sessionIds lists every open window including minimized ones', () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    expect(api.sessionIds).toEqual([]);
    api.open(10);
    api.open(20);
    api.toggleMinimized(20);
    expect(api.sessionIds).toEqual([10, 20]);
    api.close(10);
    expect(api.sessionIds).toEqual([20]);
});

test('open triggers set_view_context from current record controller', async () => {
    const calls = [];
    const env = makeEnv({
        calls,
        currentController: {
            props: { resModel: 'res.partner', resId: 42 },
        },
    });
    env.services.orm.read = async (model, ids) => {
        calls.push(['read', model, ids]);
        return [{ display_name: 'Acme' }];
    };
    const api = chatWindowService.start(env);
    api.open(11);
    for (let i = 0; i < 5; i++) {
        await Promise.resolve();
    }
    const setCalls = calls.filter(
        (c) => c[0] === 'call' && c[2] === 'set_view_context',
    );
    expect(setCalls).toHaveLength(1);
    expect(setCalls[0][3]).toEqual([
        11,
        {
            kind: 'record',
            model: 'res.partner',
            id: 42,
            display_name: 'Acme',
        },
    ]);
});

test('open with list controller builds a list payload', async () => {
    const calls = [];
    const env = makeEnv({
        calls,
        currentController: {
            props: {
                resModel: 'sale.order',
                type: 'kanban',
                domain: [['state', '=', 'sale']],
            },
        },
    });
    const api = chatWindowService.start(env);
    api.open(21);
    for (let i = 0; i < 5; i++) {
        await Promise.resolve();
    }
    const setCalls = calls.filter(
        (c) => c[0] === 'call' && c[2] === 'set_view_context',
    );
    expect(setCalls).toHaveLength(1);
    expect(setCalls[0][3][1]).toEqual({
        kind: 'list',
        model: 'sale.order',
        view_type: 'kanban',
        domain: [['state', '=', 'sale']],
    });
});

test('open without a current controller skips context dispatch', async () => {
    const calls = [];
    const api = chatWindowService.start(makeEnv({ calls }));
    api.open(33);
    for (let i = 0; i < 3; i++) {
        await Promise.resolve();
    }
    const setCalls = calls.filter(
        (c) => c[0] === 'call' && c[2] === 'set_view_context',
    );
    expect(setCalls).toEqual([]);
});
