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

import { AISessionBox } from '@muk_ai_chatter/chatter/session_box/session_box';

describe.current.tags('muk_ai_chatter');
defineMailModels();

/**
 * Answer the session summary of the record and count the calls.
 * @param {object[]} entries the session entries listed
 * @param {number} [total] the number of linked sessions
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
 * Build a session entry of the summary.
 * @param {object} [values] the values differing from the defaults
 * @returns {object} the entry
 */
function entry(values = {}) {
    return {
        id: 1,
        name: 'Session',
        state: 'done',
        create_date: '2026-01-02 09:30:00',
        user_id: [serverState.userId, 'Mitchell Admin'],
        agent_id: [1, 'Chatter Agent'],
        ...values,
    };
}

/**
 * Mount the box on a record and record the actions it runs and the session
 * pushes it listens to.
 * @param {object} [props] the props differing from the defaults
 * @returns {Promise<object>} the actions, the reported counts and a push function
 */
async function mountBox(props = {}) {
    const actions = [];
    const totals = [];
    const handlers = new Map();
    mockService('bus_service', {
        subscribe: (type, handler) => handlers.set(type, handler),
        unsubscribe: () => {},
    });
    mockService('action', { doAction: (action) => actions.push(action) });
    await mountWithCleanup(AISessionBox, {
        props: {
            threadModel: 'res.partner',
            threadId: 7,
            open: true,
            onLoaded: (total) => totals.push(total),
            ...props,
        },
    });
    const push = async (payload) => {
        handlers.get('muk_ai.session_state')(payload);
        await animationFrame();
    };
    return { actions, totals, push };
}

test('the box stays closed until asked for, and reports the count meanwhile', async () => {
    stubSummary([entry({ id: 1 }), entry({ id: 2 })], 7);
    const { totals } = await mountBox({ open: false });
    expect('.mk_session_box').toHaveCount(0);
    expect(totals).toEqual([7]);
});

test('every session is listed, its state carried by the colour of a dot', async () => {
    stubSummary([
        entry({ id: 1, name: 'First run', state: 'done' }),
        entry({ id: 2, name: 'Second run', state: 'error', agent_id: false }),
        entry({ id: 3, name: 'Third run', state: 'exotic' }),
    ]);
    await mountBox();
    expect(queryAllTexts('.mk_session_box_name')).toEqual([
        'First run',
        'Second run',
        'Third run',
    ]);
    const [done, error, exotic] = queryAll('.mk_session_box_state');
    expect(done).toHaveClass('mk_state_done');
    expect(error).toHaveClass('mk_state_error');
    expect(exotic).toHaveClass('mk_state_idle');
    expect(queryAll('.mk_session_box_item').map((row) => row.title)).toEqual([
        'Chatter Agent: Done',
        'Error',
        'Chatter Agent: exotic',
    ]);
    expect('.mk_session_box_more').toHaveCount(0);
});

test('an own session opens its chat, a foreign one its form', async () => {
    stubSummary([
        entry({ id: 7, name: 'Mine' }),
        entry({ id: 9, name: 'Theirs', user_id: [serverState.userId + 1, 'Other'] }),
    ]);
    const { actions } = await mountBox();
    const [mine, theirs] = queryAll('.mk_session_box_item');
    await click(mine);
    await click(theirs);
    expect(actions[0]).toMatchObject({ tag: 'muk_ai.chat', params: { session_id: 7 } });
    expect(actions[1]).toMatchObject({ res_model: 'muk_ai.session', res_id: 9 });
});

test('a truncated list offers every session of the record', async () => {
    stubSummary([entry({ id: 4 })], 12);
    const { actions } = await mountBox();
    expect(queryFirst('.mk_session_box_more')).toHaveText('View all 12 sessions');
    await click('.mk_session_box_more');
    expect(actions[0].domain).toEqual([
        ['res_model', '=', 'res.partner'],
        ['res_id', '=', 7],
    ]);
});

test('the list follows its sessions and the ones started on its record', async () => {
    const calls = stubSummary([entry({ id: 5 })]);
    const { push } = await mountBox();
    for (const [payload, count] of [
        [{ session_id: 4, res_model: 'res.partner', res_id: 8 }, 1],
        [{ session_id: 5, res_model: false, res_id: false }, 2],
        [{ session_id: 6, res_model: 'res.partner', res_id: 7 }, 3],
    ]) {
        await push({ state: 'running', ...payload });
        expect(calls.count).toBe(count);
    }
});
