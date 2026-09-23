import { describe, expect, test } from '@odoo/hoot';
import { registry } from '@web/core/registry';
import {
    allowTranslations,
    mockService,
    runTestScope,
} from '@web/../tests/web_test_helpers';

import '@muk_web_utils/webclient/actions/debug_items';

describe.current.tags('muk_web_utils');

function manageReports(action) {
    const factory = registry.category('debug').category('action').get('manageReports');
    return runTestScope(() => factory({ action }));
}

test('no item is offered when the action has no model', async () => {
    expect(await manageReports({})).toBe(null);
});

test('the item is placed in the ui section after the filters item', async () => {
    allowTranslations();
    const item = await manageReports({ res_model: 'res.partner' });
    expect(item.type).toBe('item');
    expect(String(item.description)).toBe('Reports');
    expect(item.section).toBe('ui');
    expect(item.sequence).toBe(265);
});

test('the callback opens the reports of the current model', async () => {
    const actions = [];
    mockService('action', {
        doAction(action) {
            actions.push(action);
        },
    });
    const item = await manageReports({ res_model: 'sale.order' });
    item.callback();
    expect(actions).toHaveLength(1);
    expect(actions[0].res_model).toBe('ir.actions.report');
    expect(actions[0].type).toBe('ir.actions.act_window');
    expect(actions[0].domain).toEqual([['model', '=', 'sale.order']]);
    expect(actions[0].views).toEqual([
        [false, 'list'],
        [false, 'form'],
    ]);
});
