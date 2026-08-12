import { describe, expect, test } from '@odoo/hoot';
import {
    animationFrame,
    click,
    queryAll,
    queryAllTexts,
    queryFirst,
} from '@odoo/hoot-dom';
import {
    mockService,
    mountWithCleanup,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { Chatter } from '@mail/chatter/web_portal/chatter';

import { AISessionBox } from '@muk_ai_chatter/chatter/ai_session_box';
import '@muk_ai_chatter/chatter/chatter_patch';

describe.current.tags('muk_ai_chatter');
defineMailModels();

const THREAD_ID = 1;

/**
 * Install a bus mock and return the notification types subscribed to.
 * @returns {Array<{type: string, handler: Function}>} the registered handlers
 */
function mockBus() {
    const listeners = [];
    mockService('bus_service', {
        subscribe(type, handler) {
            listeners.push({ type, handler });
        },
        unsubscribe() {},
    });
    return listeners;
}

/**
 * Install an action-service mock and return the actions it is asked to run.
 * @returns {Array<object>} the action descriptors passed to `doAction`
 */
function mockActions() {
    const actions = [];
    mockService('action', {
        doAction: (action) => {
            actions.push(action);
            return Promise.resolve();
        },
    });
    return actions;
}

/**
 * Stub `get_ai_sessions_summary` and count how many times it is called.
 * @param {Array<object>} entries the session entries the summary returns
 * @param {number} [total] the total session count, defaulting to `entries.length`
 * @returns {{count: number}} a live counter of the summary calls
 */
function stubSummary(entries, total = entries.length) {
    const calls = { count: 0 };
    onRpc('res.partner', 'get_ai_sessions_summary', ({ args }) => {
        calls.count += 1;
        return { [args[0][0]]: { entries, total } };
    });
    return calls;
}

/**
 * Build a session summary entry with overridable defaults.
 * @param {object} [values] the fields overriding the defaults
 * @returns {object} the summary entry
 */
function makeEntry(values = {}) {
    return {
        id: 1,
        name: 'Session',
        state: 'done',
        create_date: '2026-01-02T09:30:00',
        user_id: [serverState.userId, 'Mitchell Admin'],
        agent_id: [1, 'Chatter Agent'],
        ...values,
    };
}

/**
 * Mount the session box bound to the fixture thread.
 * @returns {Promise<AISessionBox>} the mounted component
 */
function mountBox(open = true) {
    return mountWithCleanup(AISessionBox, {
        props: { threadModel: 'res.partner', threadId: THREAD_ID, open },
    });
}

test('the chatter registers the AI session box as a sub-component', async () => {
    expect(Chatter.components.AISessionBox).toBe(AISessionBox);
});

test('nothing is shown until the topbar toggle asks for it', async () => {
    mockBus();
    mockActions();
    stubSummary([makeEntry({ id: 1 })]);
    await mountBox(false);
    expect('.o-mail-AISessionBox').toHaveCount(0);
});

test('the total is reported so the toggle can carry a count', async () => {
    mockBus();
    mockActions();
    stubSummary([makeEntry({ id: 1 }), makeEntry({ id: 2 })], 7);
    const totals = [];
    await mountWithCleanup(AISessionBox, {
        props: {
            threadModel: 'res.partner',
            threadId: THREAD_ID,
            open: false,
            onLoaded: (total) => totals.push(total),
        },
    });
    expect(totals).toEqual([7]);
});

test('nothing is rendered when the record has no AI session', async () => {
    mockBus();
    mockActions();
    stubSummary([]);
    await mountBox();
    expect('.o-mail-AISessionBox').toHaveCount(0);
});

test('every session is listed, its state carried by the colour of a dot', async () => {
    mockBus();
    mockActions();
    stubSummary([
        makeEntry({ id: 1, name: 'First run', state: 'done' }),
        makeEntry({ id: 2, name: 'Second run', state: 'error' }),
        makeEntry({ id: 3, name: 'Third run', state: 'schedule' }),
    ]);
    await mountBox();
    expect(queryAllTexts('.o-mail-AISessionBox-name')).toEqual([
        'First run',
        'Second run',
        'Third run',
    ]);
    const dots = queryAll('.o-mail-AISessionBox-state');
    expect(dots[0]).toHaveClass('o-state-done');
    expect(dots[1]).toHaveClass('o-state-error');
    expect(dots[2]).toHaveClass('o-state-busy');
    expect(dots[0]).toHaveText('');
});

test('the word the dot stands for is offered on hover', async () => {
    mockBus();
    mockActions();
    stubSummary([makeEntry({ id: 1, name: 'First run', state: 'done' })]);
    await mountBox();
    expect(queryFirst('.o-mail-AISessionBox-item')).toHaveAttribute(
        'title',
        'Chatter Agent — Done',
    );
});

test('an unknown state falls back to the neutral dot', async () => {
    mockBus();
    mockActions();
    stubSummary([makeEntry({ state: 'exotic' })]);
    await mountBox();
    expect('.o-mail-AISessionBox-state').toHaveClass('o-state-idle');
    expect(queryFirst('.o-mail-AISessionBox-item')).toHaveAttribute(
        'title',
        'Chatter Agent — exotic',
    );
});

test('clicking an own session opens the live chat', async () => {
    mockBus();
    const actions = mockActions();
    stubSummary([makeEntry({ id: 7, name: 'Mine', state: 'running' })]);
    await mountBox();
    await click('.o-mail-AISessionBox-item');
    await animationFrame();
    expect(actions).toHaveLength(1);
    expect(actions[0].type).toBe('ir.actions.client');
    expect(actions[0].tag).toBe('muk_ai.chat');
    expect(actions[0].params).toEqual({ session_id: 7 });
});

test('clicking a foreign session opens the session form instead', async () => {
    mockBus();
    const actions = mockActions();
    stubSummary([
        makeEntry({
            id: 9,
            name: 'Theirs',
            user_id: [serverState.userId + 1, 'Other'],
        }),
    ]);
    await mountBox();
    await click('.o-mail-AISessionBox-item');
    await animationFrame();
    expect(actions).toHaveLength(1);
    expect(actions[0].type).toBe('ir.actions.act_window');
    expect(actions[0].res_model).toBe('muk_ai.session');
    expect(actions[0].res_id).toBe(9);
});

test('the view-all button appears only when the list is truncated', async () => {
    mockBus();
    const actions = mockActions();
    stubSummary([makeEntry({ id: 4 })], 12);
    await mountBox();
    expect('.o-mail-AISessionBox-more').toHaveCount(1);
    await click('.o-mail-AISessionBox-more');
    await animationFrame();
    expect(actions[0].domain).toEqual([
        ['res_model', '=', 'res.partner'],
        ['res_id', '=', THREAD_ID],
    ]);
});

test('a session push only refetches when it targets a listed session', async () => {
    const listeners = mockBus();
    mockActions();
    const calls = stubSummary([makeEntry({ id: 5 })]);
    await mountBox();
    expect(calls.count).toBe(1);
    expect(listeners.map((entry) => entry.type)).toEqual([
        'muk_ai.session_state',
        'muk_ai.event',
    ]);
    const { handler } = listeners[0];
    handler({ session_id: 4 });
    await animationFrame();
    expect(calls.count).toBe(1);
    handler({});
    await animationFrame();
    expect(calls.count).toBe(1);
    handler({ session_id: 5 });
    await animationFrame();
    expect(calls.count).toBe(2);
});
