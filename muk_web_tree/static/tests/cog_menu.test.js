import { expect, test } from '@odoo/hoot';
import { contains, mountView, patchWithCleanup } from '@web/../tests/web_test_helpers';
import { download } from '@web/core/network/download';

import { collapseAllItem } from '@muk_web_group/search/collapse_all/collapse_all';
import { expandAllItem } from '@muk_web_group/search/expand_all/expand_all';

import { defineTreeModels, rowNames, TREE_ARCH } from './helpers/models';

defineTreeModels();

test.tags('muk_web_tree', 'desktop');
test('expand all and collapse all unfold the tree rows', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect(rowNames()).toEqual([
        'Alpha',
        'Alpha One',
        'Alpha Two',
        'Alpha Two Leaf',
        'Beta',
    ]);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_collapse_all_menu').click();
    expect(rowNames()).toEqual(['Alpha', 'Beta']);
});

test.tags('muk_web_tree', 'desktop');
test('expand all unfolds the groups of a grouped treelist', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        groupBy: ['parent_id'],
    });
    expect('.o_data_row').toHaveCount(0);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('.o_data_row').toHaveCount(5);
    expect('.mk_treelist_toggle').toHaveCount(0);
});

test.tags('muk_web_tree');
test('cog menu entries show on any treelist', async () => {
    const makeEnv = (viewType, groupBy) => ({
        config: { viewType },
        searchModel: { groupBy },
        services: { ui: { isSmall: false } },
    });
    for (const item of [expandAllItem, collapseAllItem]) {
        expect(await item.isDisplayed(makeEnv('treelist', []))).toBe(true);
        expect(await item.isDisplayed(makeEnv('treelist', ['parent_id']))).toBe(true);
        expect(await item.isDisplayed(makeEnv('list', []))).toBe(false);
        expect(await item.isDisplayed(makeEnv('list', ['parent_id']))).toBe(true);
    }
});

test.tags('muk_web_tree', 'desktop');
test('import and export show on a treelist', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        config: { actionType: 'ir.actions.act_window' },
    });
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    expect('.o_import_menu').toHaveCount(1);
    expect('.o_export_all_menu').toHaveCount(1);
});

test.tags('muk_web_tree', 'desktop');
test('export all sends the parent field of the tree', async () => {
    patchWithCleanup(download, {
        _download: (options) => {
            const { context, fields } = JSON.parse(options.data.data);
            expect.step([options.url, context.treelist_parent_field, fields.length]);
            return Promise.resolve();
        },
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        config: { actionType: 'ir.actions.act_window' },
    });
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.o_export_all_menu').click();
    expect.verifySteps([['/web/export/xlsx', 'parent_id', 2]]);
});
