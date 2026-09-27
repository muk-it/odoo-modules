import { describe, expect, test } from '@odoo/hoot';
import { registry } from '@web/core/registry';
import { mockService, runTestScope } from '@web/../tests/web_test_helpers';

import '@muk_web_utils/webclient/actions/client_actions';

describe.current.tags('muk_web_utils');

function runMultiAction(action) {
    const multiAction = registry.category('actions').get('multi_actions');
    return runTestScope(() => multiAction(null, action));
}

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
