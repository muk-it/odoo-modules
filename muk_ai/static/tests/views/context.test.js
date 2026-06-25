import { describe, expect, test } from '@odoo/hoot';

import {
    captureViewContext,
    makeGraphContextDispatch,
    makeListContextDispatch,
    makePivotContextDispatch,
    probeCurrentView,
    seedSessionContext,
} from '@muk_ai/views/context';

describe.current.tags('muk_ai');

function makeController({
    sessionIds = [1],
    model,
    metaData,
    searchModel,
    config,
} = {}) {
    const calls = [];
    const orm = {
        call: (...args) => {
            calls.push(args);
            return Promise.resolve({});
        },
    };
    const env = {
        services: {
            orm,
            'muk_ai.chat_window': {
                get sessionIds() {
                    return sessionIds;
                },
            },
        },
        searchModel,
        config,
    };
    return { env, calls, model, metaData };
}

test('captureViewContext noops when chat_window service missing', async () => {
    const calls = [];
    const env = {
        services: {
            orm: {
                call: (...a) => {
                    calls.push(a);
                    return Promise.resolve({});
                },
            },
        },
    };
    captureViewContext(env, { kind: 'list', model: 'res.partner' });
    expect(calls).toEqual([]);
});

test('captureViewContext noops when no open windows', () => {
    const calls = [];
    const env = {
        services: {
            orm: {
                call: (...a) => {
                    calls.push(a);
                    return Promise.resolve({});
                },
            },
            'muk_ai.chat_window': {
                get sessionIds() {
                    return [];
                },
            },
        },
    };
    captureViewContext(env, { kind: 'list', model: 'res.partner' });
    expect(calls).toEqual([]);
});

test('captureViewContext noops when payload has no model', () => {
    const calls = [];
    const env = {
        services: {
            orm: {
                call: (...a) => {
                    calls.push(a);
                    return Promise.resolve({});
                },
            },
            'muk_ai.chat_window': {
                get sessionIds() {
                    return [7];
                },
            },
        },
    };
    captureViewContext(env, { kind: 'list' });
    captureViewContext(env, null);
    expect(calls).toEqual([]);
});

test('captureViewContext dispatches set_view_context with silent orm if available', async () => {
    const calls = [];
    const silent = {
        call: (...a) => {
            calls.push(['silent', ...a]);
            return Promise.resolve({});
        },
    };
    const orm = {
        call: (...a) => {
            calls.push(['loud', ...a]);
            return Promise.resolve({});
        },
        silent,
    };
    const env = {
        services: {
            orm,
            'muk_ai.chat_window': {
                get sessionIds() {
                    return [9];
                },
            },
        },
    };
    captureViewContext(env, { kind: 'list', model: 'sale.order' });
    await Promise.resolve();
    expect(calls[0][0]).toBe('silent');
    expect(calls[0][1]).toBe('muk_ai.session');
    expect(calls[0][2]).toBe('set_view_context');
    expect(calls[0][3]).toEqual([9, { kind: 'list', model: 'sale.order' }]);
});

test('captureViewContext dispatches to every open window', async () => {
    const calls = [];
    const env = {
        services: {
            orm: {
                call: (...a) => {
                    calls.push(a);
                    return Promise.resolve({});
                },
            },
            'muk_ai.chat_window': {
                get sessionIds() {
                    return [3, 5];
                },
            },
        },
    };
    captureViewContext(env, { kind: 'record', model: 'res.partner', id: 1 });
    await Promise.resolve();
    expect(calls).toHaveLength(2);
    expect(calls[0][2][0]).toBe(3);
    expect(calls[1][2][0]).toBe(5);
});

test('makeListContextDispatch builds payload with view_type + domain and only fires on change', async () => {
    const ctrl = makeController({
        model: { root: { resModel: 'res.partner' } },
        searchModel: { domain: [['active', '=', true]] },
    });
    const dispatch = makeListContextDispatch(ctrl, 'kanban');
    dispatch();
    dispatch();
    await Promise.resolve();
    expect(ctrl.calls).toHaveLength(1);
    const [[model, method, args]] = ctrl.calls;
    expect(model).toBe('muk_ai.session');
    expect(method).toBe('set_view_context');
    expect(args[1]).toEqual({
        kind: 'list',
        model: 'res.partner',
        view_type: 'kanban',
        domain: [['active', '=', true]],
    });
});

test('makeListContextDispatch bails without resModel', () => {
    const ctrl = makeController({
        model: { root: {} },
        config: {},
    });
    const dispatch = makeListContextDispatch(ctrl, 'list');
    dispatch();
    expect(ctrl.calls).toEqual([]);
});

test('makeListContextDispatch omits empty domain', async () => {
    const ctrl = makeController({
        model: { root: { resModel: 'res.partner' } },
        searchModel: { domain: [] },
    });
    makeListContextDispatch(ctrl, 'list')();
    await Promise.resolve();
    expect(ctrl.calls[0][2][1]).toEqual({
        kind: 'list',
        model: 'res.partner',
        view_type: 'list',
    });
});

test('makePivotContextDispatch forwards active measures + groupbys', async () => {
    const ctrl = makeController({
        model: {
            metaData: {
                resModel: 'sale.order',
                activeMeasures: ['amount_total'],
                fullRowGroupBys: ['partner_id'],
                fullColGroupBys: ['user_id'],
            },
        },
        searchModel: { domain: [['state', '=', 'sale']] },
    });
    makePivotContextDispatch(ctrl)();
    await Promise.resolve();
    const payload = ctrl.calls[0][2][1];
    expect(payload.kind).toBe('pivot');
    expect(payload.pivot_measures).toEqual(['amount_total']);
    expect(payload.pivot_row_groupby).toEqual(['partner_id']);
    expect(payload.pivot_column_groupby).toEqual(['user_id']);
    expect(payload.domain).toEqual([['state', '=', 'sale']]);
});

test('makeGraphContextDispatch uses meta mode + measure + groupBy fieldNames', async () => {
    const ctrl = makeController({
        model: {
            metaData: {
                resModel: 'sale.order',
                mode: 'pie',
                measure: 'amount_total',
                groupBy: [{ fieldName: 'partner_id' }, 'user_id'],
                order: 'ASC',
            },
        },
        searchModel: { domain: [] },
    });
    makeGraphContextDispatch(ctrl)();
    await Promise.resolve();
    const payload = ctrl.calls[0][2][1];
    expect(payload.kind).toBe('graph');
    expect(payload.graph_mode).toBe('pie');
    expect(payload.graph_measure).toBe('amount_total');
    expect(payload.graph_groupbys).toEqual(['partner_id', 'user_id']);
    expect(payload.graph_order).toBe('ASC');
});

test('makeGraphContextDispatch uses defaults when meta is missing', async () => {
    const ctrl = makeController({
        model: { metaData: { resModel: 'res.partner' } },
    });
    makeGraphContextDispatch(ctrl)();
    await Promise.resolve();
    const payload = ctrl.calls[0][2][1];
    expect(payload.graph_mode).toBe('bar');
    expect(payload.graph_measure).toBe('__count');
    expect(payload.graph_groupbys).toEqual([]);
});

test('dispatchers bail with no open windows (no RPC)', () => {
    const ctrl = makeController({
        sessionIds: [],
        model: { root: { resModel: 'res.partner' } },
        searchModel: { domain: [] },
    });
    makeListContextDispatch(ctrl, 'list')();
    expect(ctrl.calls).toEqual([]);
});

test('probeCurrentView returns null without a current controller', async () => {
    const env = { services: { action: { currentController: null } } };
    expect(await probeCurrentView(env)).toBe(null);
});

test('probeCurrentView builds a record payload with display_name', async () => {
    const env = {
        services: {
            action: {
                currentController: { props: { resModel: 'res.partner', resId: 5 } },
            },
            orm: { read: async () => [{ display_name: 'Acme' }] },
        },
    };
    expect(await probeCurrentView(env)).toEqual({
        kind: 'record',
        model: 'res.partner',
        id: 5,
        display_name: 'Acme',
    });
});

test('probeCurrentView falls back to a list payload without resId', async () => {
    const env = {
        services: {
            action: {
                currentController: {
                    props: {
                        resModel: 'sale.order',
                        type: 'kanban',
                        domain: [['state', '=', 'sale']],
                    },
                },
            },
            orm: { read: async () => [] },
        },
    };
    expect(await probeCurrentView(env)).toEqual({
        kind: 'list',
        model: 'sale.order',
        view_type: 'kanban',
        domain: [['state', '=', 'sale']],
    });
});

test('seedSessionContext probes and dispatches set_view_context', async () => {
    const calls = [];
    const env = {
        services: {
            action: {
                currentController: { props: { resModel: 'res.partner', resId: 9 } },
            },
            orm: {
                call: (...a) => {
                    calls.push(['call', ...a]);
                    return Promise.resolve({});
                },
                read: async () => [{ display_name: 'Globex' }],
            },
        },
    };
    const ok = await seedSessionContext(env, 42);
    expect(ok).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0][1]).toBe('muk_ai.session');
    expect(calls[0][2]).toBe('set_view_context');
    expect(calls[0][3]).toEqual([
        42,
        {
            kind: 'record',
            model: 'res.partner',
            id: 9,
            display_name: 'Globex',
        },
    ]);
});

test('seedSessionContext respects an explicit payload over the probe', async () => {
    const calls = [];
    const env = {
        services: {
            action: {
                currentController: { props: { resModel: 'res.partner', resId: 9 } },
            },
            orm: {
                call: (...a) => {
                    calls.push(['call', ...a]);
                    return Promise.resolve({});
                },
                read: async () => [{ display_name: 'Globex' }],
            },
        },
    };
    const carry = { kind: 'list', model: 'sale.order', view_type: 'list' };
    const ok = await seedSessionContext(env, 13, carry);
    expect(ok).toBe(true);
    expect(calls).toHaveLength(1);
    expect(calls[0][3]).toEqual([13, carry]);
});

test('seedSessionContext returns false without a sessionId', async () => {
    const calls = [];
    const env = {
        services: {
            orm: {
                call: (...a) => {
                    calls.push(a);
                    return Promise.resolve({});
                },
            },
        },
    };
    expect(await seedSessionContext(env, null)).toBe(false);
    expect(calls).toEqual([]);
});

test('seedSessionContext returns false when there is nothing to pin', async () => {
    const calls = [];
    const env = {
        services: {
            action: { currentController: null },
            orm: {
                call: (...a) => {
                    calls.push(a);
                    return Promise.resolve({});
                },
            },
        },
    };
    expect(await seedSessionContext(env, 7)).toBe(false);
    expect(calls).toEqual([]);
});
