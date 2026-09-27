import { describe, expect, test } from '@odoo/hoot';
import { registry } from '@web/core/registry';
import { mockService, runTestScope } from '@web/../tests/web_test_helpers';

import '@muk_web_utils/webclient/actions/debug_items';

describe.current.tags('muk_web_utils');

function manageReports(action) {
    const factory = registry.category('debug').category('action').get('manageReports');
    return runTestScope(() => factory({ action }));
}

test('no item is offered when the action has no model', async () => {
    expect(await manageReports({})).toBe(null);
});

test('the item opens the reports of the current model', async () => {
    mockService('action', {
        doAction(action) {
            expect.step(action.res_model);
            expect(action.domain).toEqual([['model', '=', 'sale.order']]);
        },
    });
    const item = await manageReports({ res_model: 'sale.order' });
    item.callback();
    expect.verifySteps(['ir.actions.report']);
});
