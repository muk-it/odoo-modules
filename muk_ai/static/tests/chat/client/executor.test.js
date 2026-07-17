import { describe, expect, test } from '@odoo/hoot';
import { waitUntil } from '@odoo/hoot-dom';

import { makeClientToolListener, parseArguments } from '@muk_ai/chat/client/executor';

describe.current.tags('muk_ai');

function makeHarness({ sessionIds = [11], execute } = {}) {
    const calls = [];
    const executed = [];
    const listener = makeClientToolListener({
        orm: {
            call: async (model, method, args, kwargs) => {
                calls.push({ model, method, args, kwargs });
                return {};
            },
        },
        chatWindow: {
            get sessionIds() {
                return sessionIds;
            },
        },
        contains: (name) => name === 'adjust_search',
        execute:
            execute ||
            (async (name, args) => {
                executed.push({ name, args });
                return { ok: true };
            }),
    });
    return { listener, calls, executed };
}

function actionEvent(overrides = {}, payloadOverrides = {}) {
    return {
        type: 'log',
        session_id: 11,
        payload: {
            kind: 'client_action',
            call_id: 'c1',
            name: 'adjust_search',
            arguments: '{"filters":["a"]}',
            ...payloadOverrides,
        },
        ...overrides,
    };
}

test('parseArguments accepts objects, JSON strings and empty payloads', () => {
    expect(parseArguments({ a: 1 })).toEqual({ a: 1 });
    expect(parseArguments('{"a":1}')).toEqual({ a: 1 });
    expect(parseArguments('')).toEqual({});
    expect(parseArguments(undefined)).toEqual({});
});

test('parseArguments flags corrupt or truncated payloads', () => {
    expect(parseArguments('{"a":1')).toBe(null);
    expect(parseArguments('"just a string"')).toBe(null);
    expect(parseArguments('42')).toBe(null);
});

test('executes a matching action and submits the result', async () => {
    const { listener, calls, executed } = makeHarness();
    listener(actionEvent());
    await waitUntil(() => calls.length === 1);
    expect(executed).toHaveLength(1);
    expect(executed[0].args).toEqual({ filters: ['a'] });
    expect(calls[0].method).toBe('submit_client_result');
    expect(calls[0].args).toEqual([11, 'c1', { ok: true }]);
});

test('ignores events for sessions this tab does not hold', async () => {
    const { listener, calls } = makeHarness({ sessionIds: [99] });
    listener(actionEvent());
    // same listener with a matching event still works afterwards
    const held = makeHarness();
    held.listener(actionEvent(undefined, { call_id: 'c-held' }));
    await waitUntil(() => held.calls.length === 1);
    expect(calls).toHaveLength(0);
});

test('ignores unknown tools and non-client-action events', async () => {
    const { listener, calls } = makeHarness();
    listener(actionEvent(undefined, { name: 'other_tool', call_id: 'c2' }));
    listener(actionEvent({ type: 'state' }, { call_id: 'c3' }));
    listener({ type: 'log', session_id: 11, payload: { kind: 'ask_user' } });
    const ok = makeHarness();
    ok.listener(actionEvent(undefined, { call_id: 'c-ok' }));
    await waitUntil(() => ok.calls.length === 1);
    expect(calls).toHaveLength(0);
});

test('deduplicates repeated call ids', async () => {
    const { listener, calls } = makeHarness();
    listener(actionEvent(undefined, { call_id: 'c-dup' }));
    listener(actionEvent(undefined, { call_id: 'c-dup' }));
    await waitUntil(() => calls.length === 1);
    expect(calls).toHaveLength(1);
});

test('rejects the action when the handler throws', async () => {
    const { listener, calls } = makeHarness({
        execute: async () => {
            throw new Error('boom');
        },
    });
    listener(actionEvent(undefined, { call_id: 'c-err' }));
    await waitUntil(() => calls.length === 1);
    expect(calls[0].method).toBe('reject_client_action');
    expect(calls[0].kwargs.reason).toMatch(/boom/);
});

test('rejects corrupt arguments without executing the handler', async () => {
    const { listener, calls, executed } = makeHarness();
    listener(actionEvent(undefined, { call_id: 'c-bad', arguments: '{"trunc' }));
    await waitUntil(() => calls.length === 1);
    expect(executed).toHaveLength(0);
    expect(calls[0].method).toBe('reject_client_action');
    expect(calls[0].kwargs.reason).toMatch(/corrupt or truncated/);
});
