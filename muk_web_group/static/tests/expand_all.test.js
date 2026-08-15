import { expect, test } from '@odoo/hoot';
import { contains, mountView, onRpc } from '@web/../tests/web_test_helpers';

import { expandAllItem } from '@muk_web_group/search/expand_all/expand_all';
import '@muk_web_group/search/collapse_all/collapse_all';

import { defineGroupModels, KANBAN_ARCH, LIST_ARCH } from './helpers/models';

defineGroupModels();

function makeEnv(viewType, isGrouped) {
    return { config: { viewType }, model: { root: { isGrouped } } };
}

test.tags('muk_web_group');
test('expand all unfolds every group of a grouped list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: LIST_ARCH,
    });
    expect('.o_group_header').toHaveCount(2);
    expect('tbody tr.o_data_row').toHaveCount(0);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
});

test.tags('muk_web_group');
test('expand all unfolds nested groups down to the records', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id', 'stage'],
        arch: LIST_ARCH,
    });
    expect('.o_group_header').toHaveCount(2);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
    expect('.o_group_header').toHaveCount(5);
});

test.tags('muk_web_group');
test('expand all unfolds every column of a grouped kanban', async () => {
    await mountView({
        type: 'kanban',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: KANBAN_ARCH,
    });
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_collapse_all_menu').click();
    expect('.o_kanban_group.o_column_folded').toHaveCount(2);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('.o_kanban_group.o_column_folded').toHaveCount(0);
    expect('.o_kanban_record').toHaveCount(3);
});

test.tags('muk_web_group');
test('expand all is a no-op when every group is already unfolded', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: LIST_ARCH,
    });
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
});

test.tags('muk_web_group');
test('expand all loads every group in a single batched reload', async () => {
    const calls = [];
    onRpc('product', 'web_search_read', ({ method }) => {
        calls.push(method);
    });
    onRpc('product', 'web_read_group', ({ method }) => {
        calls.push(method);
    });
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id'],
        arch: LIST_ARCH,
    });
    calls.length = 0;
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
    expect(calls.filter((call) => call === 'web_search_read').length).toBe(0);
    expect(calls.length).toBe(1);
});

test.tags('muk_web_group');
test('expand all loads every nesting level in a single batched reload', async () => {
    const calls = [];
    onRpc('product', 'web_search_read', ({ method }) => {
        calls.push(method);
    });
    onRpc('product', 'web_read_group', ({ method }) => {
        calls.push(method);
    });
    await mountView({
        type: 'list',
        resModel: 'product',
        groupBy: ['category_id', 'stage'],
        arch: LIST_ARCH,
    });
    calls.length = 0;
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains('.mk_expand_all_menu').click();
    expect('tbody tr.o_data_row').toHaveCount(3);
    expect('.o_group_header').toHaveCount(5);
    expect(calls.filter((call) => call === 'web_search_read').length).toBe(0);
    expect(calls.length).toBe(2);
});

test.tags('muk_web_group');
test('expand all is hidden in an ungrouped list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: LIST_ARCH,
    });
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    expect('.mk_expand_all_menu').toHaveCount(0);
});

test.tags('muk_web_group');
test('expand all is only offered for grouped list and kanban views', async () => {
    expect(await expandAllItem.isDisplayed(makeEnv('list', true))).toBe(true);
    expect(await expandAllItem.isDisplayed(makeEnv('kanban', true))).toBe(true);
    expect(await expandAllItem.isDisplayed(makeEnv('list', false))).toBe(false);
    expect(await expandAllItem.isDisplayed(makeEnv('form', true))).toBe(false);
    expect(await expandAllItem.isDisplayed(makeEnv('pivot', true))).toBe(false);
});
