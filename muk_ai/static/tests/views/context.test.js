import { describe, expect, test } from '@odoo/hoot';

import {
    captureViewContext,
    makeGraphContextDispatch,
    makeListContextDispatch,
    makePivotContextDispatch,
} from '@muk_ai/views/context';

describe.current.tags('muk_ai');


function makeController({ activeSessionId = 1, model, metaData, searchModel, config } = {}) {
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
                get activeSessionId() { return activeSessionId; },
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
            orm: { call: (...a) => { calls.push(a); return Promise.resolve({}); } },
        },
    };
    captureViewContext(env, { kind: 'list', model: 'res.partner' });
    expect(calls).toEqual([]);
});

test('captureViewContext noops when no active session', () => {
    const calls = [];
    const env = {
        services: {
            orm: { call: (...a) => { calls.push(a); return Promise.resolve({}); } },
            'muk_ai.chat_window': { get activeSessionId() { return null; } },
        },
    };
    captureViewContext(env, { kind: 'list', model: 'res.partner' });
    expect(calls).toEqual([]);
});

test('captureViewContext noops when payload has no model', () => {
    const calls = [];
    const env = {
        services: {
            orm: { call: (...a) => { calls.push(a); return Promise.resolve({}); } },
            'muk_ai.chat_window': { get activeSessionId() { return 7; } },
        },
    };
    captureViewContext(env, { kind: 'list' });
    captureViewContext(env, null);
    expect(calls).toEqual([]);
});

test('captureViewContext dispatches set_view_context with silent orm if available', async () => {
    const calls = [];
    const silent = { call: (...a) => { calls.push(['silent', ...a]); return Promise.resolve({}); } };
    const orm = { call: (...a) => { calls.push(['loud', ...a]); return Promise.resolve({}); }, silent };
    const env = {
        services: {
            orm,
            'muk_ai.chat_window': { get activeSessionId() { return 9; } },
        },
    };
    captureViewContext(env, { kind: 'list', model: 'sale.order' });
    await Promise.resolve();
    expect(calls[0][0]).toBe('silent');
    expect(calls[0][1]).toBe('muk_ai.session');
    expect(calls[0][2]).toBe('set_view_context');
    expect(calls[0][3]).toEqual([9, { kind: 'list', model: 'sale.order' }]);
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
        kind: 'list', model: 'res.partner', view_type: 'list',
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


test('dispatchers bail with no active session (no RPC)', () => {
    const ctrl = makeController({
        activeSessionId: null,
        model: { root: { resModel: 'res.partner' } },
        searchModel: { domain: [] },
    });
    makeListContextDispatch(ctrl, 'list')();
    expect(ctrl.calls).toEqual([]);
});
