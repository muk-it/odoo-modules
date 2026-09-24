import { expect, test } from '@odoo/hoot';
import { contains, mountView } from '@web/../tests/web_test_helpers';

import { collapseAllItem } from '@muk_web_group/search/collapse_all/collapse_all';
import '@muk_web_group/search/expand_all/expand_all';

import { defineGroupModels, KANBAN_ARCH, LIST_ARCH } from './helpers/models';

defineGroupModels();

function makeEnv(viewType, groupBy = [], isSmall = false) {
    return {
        config: { viewType },
        searchModel: { groupBy },
        services: { ui: { isSmall } },
    };
}

async function openCogMenu() {
    await contains('.o_cp_action_menus .dropdown-toggle').click();
}

test.tags('muk_web_group');
test('collapse all folds every group of a grouped list again', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: LIST_ARCH,
    });
    await openCogMenu();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
    await openCogMenu();
    await contains('.mk_collapse_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(0);
    expect('.o_group_header').toHaveCount(2);
});

test.tags('muk_web_group');
test('collapse all folds nested groups from the innermost level up', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id', 'stage'],
        arch: LIST_ARCH,
    });
    await openCogMenu();
    await contains('.mk_expand_all_menu').click();
    expect('.o_group_header').toHaveCount(5);
    await openCogMenu();
    await contains('.mk_collapse_all_menu').click();
    expect('.o_group_header').toHaveCount(2);
    expect('tbody tr.o_data_row').toHaveCount(0);
});

test.tags('muk_web_group', 'desktop');
test('collapse all folds every column of a grouped kanban', async () => {
    await mountView({
        type: 'kanban',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: KANBAN_ARCH,
    });
    expect('.o_kanban_record').toHaveCount(3);
    await openCogMenu();
    await contains('.mk_collapse_all_menu').click();
    expect('.o_kanban_group.o_column_folded').toHaveCount(2);
    expect('.o_kanban_record').toHaveCount(0);
});

test.tags('muk_web_group');
test('collapse all is a no-op when every group is already folded', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: LIST_ARCH,
    });
    expect('tbody tr.o_data_row').toHaveCount(0);
    await openCogMenu();
    await contains('.mk_collapse_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(0);
    expect('.o_group_header').toHaveCount(2);
});

test.tags('muk_web_group');
test('collapse all is hidden in an ungrouped list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: LIST_ARCH,
    });
    await openCogMenu();
    expect('.mk_collapse_all_menu').toHaveCount(0);
});

test.tags('muk_web_group');
test('collapse all is not offered for a kanban on a small screen', async () => {
    expect(
        await collapseAllItem.isDisplayed(makeEnv('kanban', ['category_id'], true)),
    ).toBe(false);
    expect(
        await collapseAllItem.isDisplayed(makeEnv('list', ['category_id'], true)),
    ).toBe(true);
});

test.tags('muk_web_group');
test('collapse all is only offered for grouped list and kanban views', async () => {
    expect(await collapseAllItem.isDisplayed(makeEnv('list', ['category_id']))).toBe(
        true,
    );
    expect(await collapseAllItem.isDisplayed(makeEnv('kanban', ['category_id']))).toBe(
        true,
    );
    expect(await collapseAllItem.isDisplayed(makeEnv('kanban'))).toBe(false);
    expect(await collapseAllItem.isDisplayed(makeEnv('form', ['category_id']))).toBe(
        false,
    );
});

test.tags('muk_web_group', 'mobile');
test('a small-screen kanban offers neither collapse all nor expand all', async () => {
    await mountView({
        type: 'kanban',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: KANBAN_ARCH,
    });
    await openCogMenu();
    expect('.o-dropdown--menu').toHaveCount(1);
    expect('.mk_collapse_all_menu').toHaveCount(0);
    expect('.mk_expand_all_menu').toHaveCount(0);
});

test.tags('muk_web_group', 'mobile');
test('a small-screen list still offers collapse all and expand all', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: LIST_ARCH,
    });
    await openCogMenu();
    expect('.mk_collapse_all_menu').toHaveCount(1);
    expect('.mk_expand_all_menu').toHaveCount(1);
});
