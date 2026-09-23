import { describe, expect, test } from '@odoo/hoot';
import { registry } from '@web/core/registry';
import { mockService, runTestScope } from '@web/../tests/web_test_helpers';

import { multiAction } from '@muk_web_utils/webclient/actions/client_actions';

describe.current.tags('muk_web_utils');

function runMultiAction(action) {
    return runTestScope(() => multiAction(null, action));
}

test('multi_actions is registered as a client action', async () => {
    expect(registry.category('actions').get('multi_actions')).toBe(multiAction);
});

test('sub-actions run in order', async () => {
    mockService('action', {
        async doAction(action) {
            expect.step(action);
        },
    });
    await runMultiAction({ params: { actions: ['first', 'second', 'third'] } });
    expect.verifySteps(['first', 'second', 'third']);
});

test('each sub-action is awaited before the next one starts', async () => {
    mockService('action', {
        doAction(action) {
            expect.step(`start:${action}`);
            return Promise.resolve().then(() => expect.step(`end:${action}`));
        },
    });
    await runMultiAction({ params: { actions: ['a', 'b'] } });
    expect.verifySteps(['start:a', 'end:a', 'start:b', 'end:b']);
});

test('a missing params or actions key runs nothing', async () => {
    mockService('action', {
        async doAction(action) {
            expect.step(action);
        },
    });
    await runMultiAction({});
    await runMultiAction({ params: {} });
    expect.verifySteps([]);
});
