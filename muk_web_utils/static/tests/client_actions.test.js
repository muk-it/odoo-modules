import { describe, expect, test } from '@odoo/hoot';
import { registry } from '@web/core/registry';

import { multiAction } from '@muk_web_utils/webclient/actions/client_actions';

describe.current.tags('muk_web_utils');

/**
 * Build a fake environment recording the actions passed to the action service.
 * @param {Array} log the array collecting the executed actions
 * @returns {object} the environment stub
 */
function makeEnv(log) {
    return {
        services: {
            action: {
                async doAction(action) {
                    log.push(action);
                },
            },
        },
    };
}

test('multi_actions is registered as a client action', async () => {
    expect(registry.category('actions').get('multi_actions')).toBe(multiAction);
});

test('sub-actions run in order', async () => {
    const log = [];
    await multiAction(makeEnv(log), {
        params: { actions: ['first', { type: 'ir.actions.act_window' }, 'third'] },
    });
    expect(log).toEqual(['first', { type: 'ir.actions.act_window' }, 'third']);
});

test('each sub-action is awaited before the next one starts', async () => {
    const order = [];
    const env = {
        services: {
            action: {
                doAction(action) {
                    order.push(`start:${action}`);
                    return Promise.resolve().then(() => {
                        order.push(`end:${action}`);
                    });
                },
            },
        },
    };
    await multiAction(env, { params: { actions: ['a', 'b'] } });
    expect(order).toEqual(['start:a', 'end:a', 'start:b', 'end:b']);
});

test('a missing params or actions key runs nothing', async () => {
    const log = [];
    await multiAction(makeEnv(log), {});
    await multiAction(makeEnv(log), { params: {} });
    expect(log).toHaveLength(0);
});
