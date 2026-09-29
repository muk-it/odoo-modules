import { after, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';

import {
    contains,
    defineModels,
    defineWebModels,
    fields,
    getService,
    mockService,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { rpcBus } from '@web/core/network/rpc';

import '@muk_web_actions/search/action_menus/action_menus';
import '@muk_web_actions/search/action_menus/bindings_cache';

const PROGRESS = '.mk_block_progress_card';

class Partner extends models.Model {
    name = fields.Char();
    _records = [1, 2, 3, 4, 5].map((id) => ({ id, name: `Partner ${id}` }));
}

class IrActionsServer extends models.Model {
    _name = 'ir.actions.server';
    name = fields.Char();
    _records = [{ id: 1, name: 'Batch Action' }];
}

class IrActionsReport extends models.Model {
    _name = 'ir.actions.report';
    name = fields.Char();
    _records = [{ id: 1, name: 'Batch Report' }];
}

defineModels([Partner, IrActionsServer, IrActionsReport]);
defineWebModels();

/**
 * Mount the partner list with a batch action, a plain action and a batch
 * report, and record every action the menus dispatch.
 * @param {object} [options]
 * @param {number} [options.limit] page size of the list
 * @param {Function} [options.doAction] replacement for the action dispatch
 */
async function mountPartners({ limit = 80, doAction } = {}) {
    mockService('action', {
        doAction:
            doAction ??
            ((id, { additionalContext, onClose }) => {
                expect.step([id, additionalContext.active_ids]);
                onClose();
            }),
    });
    await mountView({
        type: 'list',
        resModel: 'partner',
        arch: `<list limit="${limit}"><field name="name"/></list>`,
        info: {
            actionMenus: {
                action: [
                    {
                        id: 10,
                        name: 'Batch Action',
                        execute_in_batch: true,
                        execution_batch_size: 2,
                    },
                    { id: 11, name: 'Plain Action' },
                ],
                print: [
                    {
                        id: 12,
                        name: 'Batch Report',
                        execute_in_batch: true,
                        execution_batch_size: 1,
                    },
                ],
            },
        },
    });
}

/**
 * Open one of the action menus and click an item.
 * @param {string} menu label of the dropdown, ``Actions`` or ``Print``
 * @param {string} item label of the menu item
 */
async function runMenuItem(menu, item) {
    await contains(`.o_cp_action_menus .dropdown-toggle:contains(${menu})`).click();
    await contains(`.o-dropdown-item:contains(${item})`).click();
}

test.tags('muk_web_actions', 'desktop');
test('each item runs over the selection in its own slices', async () => {
    const cases = [
        [
            'Actions',
            'Batch Action',
            [
                [10, [1, 2]],
                [10, [3, 4]],
                [10, [5]],
            ],
        ],
        ['Actions', 'Plain Action', [[11, [1, 2, 3, 4, 5]]]],
        ['Print', 'Batch Report', [1, 2, 3, 4, 5].map((id) => [12, [id]])],
    ];
    await mountPartners();
    for (const [menu, item, steps] of cases) {
        await contains('thead .o_list_record_selector input').click();
        await runMenuItem(menu, item);
        await animationFrame();
        expect.verifySteps(steps);
        expect(PROGRESS).toHaveCount(0);
    }
});

test.tags('muk_web_actions', 'desktop');
test('the progress overlay follows the batches and reloads the list', async () => {
    const pending = [];
    await mountPartners({
        doAction: (id, { additionalContext, onClose }) => {
            const { promise, resolve } = Promise.withResolvers();
            pending.push(() => {
                onClose();
                resolve();
            });
            expect.step(additionalContext.active_ids);
            return promise;
        },
    });
    onRpc('web_search_read', () => expect.step('reload'));
    await contains('thead .o_list_record_selector input').click();
    await runMenuItem('Actions', 'Batch Action');
    expect.verifySteps([[1, 2]]);
    for (const [text, steps] of [
        ['Batch 0 out of 3', ['reload', [3, 4]]],
        ['Batch 1 out of 3', ['reload', [5]]],
        ['Batch 2 out of 3', ['reload']],
    ]) {
        expect(PROGRESS).toHaveText(new RegExp(text));
        pending.shift()();
        await animationFrame();
        expect.verifySteps(steps);
    }
    expect(PROGRESS).toHaveCount(0);
    expect('.o_blockUI').toHaveCount(0);
});

test.tags('muk_web_actions', 'desktop');
test('a selected domain is resolved on the server before batching', async () => {
    onRpc('partner', 'search', ({ kwargs }) => expect.step(`search:${kwargs.limit}`));
    await mountPartners({ limit: 2 });
    await contains('thead .o_list_record_selector input').click();
    await contains('.o_selection_box .o_select_domain').click();
    await runMenuItem('Actions', 'Batch Action');
    await animationFrame();
    expect.verifySteps(['search:20000', [10, [1, 2]], [10, [3, 4]], [10, [5]]]);
});

test.tags('muk_web_actions', 'desktop');
test('a failing batch stops the run and unblocks the screen', async () => {
    expect.errors(1);
    await mountPartners({
        doAction: (id, { additionalContext }) => {
            expect.step(additionalContext.active_ids);
            if (additionalContext.active_ids.includes(3)) {
                throw new Error('batch failed');
            }
        },
    });
    await contains('thead .o_list_record_selector input').click();
    await runMenuItem('Actions', 'Batch Action');
    await animationFrame();
    expect.verifySteps([
        [1, 2],
        [3, 4],
    ]);
    expect.verifyErrors(['batch failed']);
    expect(PROGRESS).toHaveCount(0);
    expect('.o_blockUI').toHaveCount(0);
});

test.tags('muk_web_actions');
test('saving an action or a report drops the cached views', async () => {
    const onClear = (ev) => expect.step(`${ev.detail}`);
    rpcBus.addEventListener('CLEAR-CACHES', onClear);
    after(() => rpcBus.removeEventListener('CLEAR-CACHES', onClear));
    await mountPartners();
    for (const [model, cleared] of [
        ['ir.actions.server', ['get_views']],
        ['ir.actions.report', ['get_views']],
        ['partner', []],
    ]) {
        await getService('orm').write(model, [1], { name: 'Renamed' });
        expect.verifySteps(cleared);
    }
});
