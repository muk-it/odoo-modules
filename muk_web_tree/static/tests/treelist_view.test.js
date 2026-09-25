import { expect, test } from '@odoo/hoot';
import { press, queryAllTexts } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { contains, mountView } from '@web/../tests/web_test_helpers';
import { browser } from '@web/core/browser/browser';

import {
    defineTreeModels,
    rowLevels,
    rowNames,
    SEARCH_ARCH,
    TREE_ARCH,
} from './helpers/models';

defineTreeModels();

test.tags('muk_web_tree', 'desktop');
test('renders the root records with a toggle on parents', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    expect('table.o_list_table').toHaveAttribute('role', 'treegrid');
    expect(rowNames()).toEqual(['Alpha', 'Beta']);
    expect(rowLevels()).toEqual(['1', '1']);
    expect('.o_data_row:eq(0) .mk_treelist_toggle').toHaveCount(1);
    expect('.o_data_row:eq(0)').toHaveAttribute('aria-expanded', 'false');
    expect('.o_data_row:eq(1) .mk_treelist_toggle').toHaveCount(0);
    expect('.o_data_row:eq(1)').not.toHaveAttribute('aria-expanded');
    expect('.o_pager_value').toHaveText('1-2');
});

test.tags('muk_web_tree', 'desktop');
test('expands and collapses rows', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Beta']);
    expect(rowLevels()).toEqual(['1', '2', '2', '1']);
    await contains('.o_data_row:eq(2) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual([
        'Alpha',
        'Alpha One',
        'Alpha Two',
        'Alpha Two Leaf',
        'Beta',
    ]);
    expect('.o_data_row:eq(3) .mk_treelist_cell').toHaveAttribute(
        'style',
        '--mk-treelist-level: 2;',
    );
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual(['Alpha', 'Beta']);
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual([
        'Alpha',
        'Alpha One',
        'Alpha Two',
        'Alpha Two Leaf',
        'Beta',
    ]);
});

test.tags('muk_web_tree', 'desktop');
test('search shows the matches under greyed ancestors', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_leaf: 1 },
    });
    expect(rowNames()).toEqual(['Alpha', 'Alpha Two', 'Alpha Two Leaf']);
    expect('.o_data_row.mk_treelist_context').toHaveCount(2);
    expect('.o_data_row:eq(2)').not.toHaveClass('mk_treelist_context');
});

test.tags('muk_web_tree', 'desktop');
test('each group shows its records as a tree', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        groupBy: ['amount'],
    });
    expect('.o_group_header').toHaveCount(5);
    await contains('.o_group_header:eq(0)').click();
    expect(rowNames()).toEqual(['Alpha']);
    expect('.o_data_row:eq(0) .mk_treelist_toggle').toHaveCount(0);
    await contains('.o_group_header:eq(2)').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha Two']);
    expect('.o_data_row:eq(1)').toHaveAttribute('aria-level', '1');
});

test.tags('muk_web_tree', 'desktop');
test('a parent inside a group expands its children of the group', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        groupBy: ['group_key'],
    });
    await contains('.o_group_header:eq(0)').click();
    expect(rowNames()).toEqual(['Alpha', 'Beta']);
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Beta']);
    expect('.o_data_row:eq(1)').toHaveAttribute('aria-level', '2');
});

test.tags('muk_web_tree', 'desktop');
test('remembers the expanded rows', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(JSON.parse(browser.localStorage.getItem('mk_treelist,category,0'))).toEqual([
        1,
    ]);
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    expect(rowNames().slice(-4)).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Beta']);
});

test.tags('muk_web_tree', 'desktop');
test('expand attribute opens every row on first load', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist expand="1"><field name="name"/></treelist>',
    });
    expect(rowNames()).toEqual([
        'Alpha',
        'Alpha One',
        'Alpha Two',
        'Alpha Two Leaf',
        'Beta',
    ]);
});

test.tags('muk_web_tree', 'desktop');
test('arrow keys expand, collapse and move to the parent', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    await contains('.o_data_row:eq(0) .mk_treelist_cell').focus();
    await press('arrowright');
    await animationFrame();
    await animationFrame();
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Beta']);
    expect('.o_data_row:eq(0) .mk_treelist_cell').toBeFocused();
    await press('arrowdown');
    expect('.o_data_row:eq(1) .mk_treelist_cell').toBeFocused();
    await press('arrowleft');
    await animationFrame();
    expect('.o_data_row:eq(0) .mk_treelist_cell').toBeFocused();
    await press('arrowleft');
    await animationFrame();
    expect(rowNames()).toEqual(['Alpha', 'Beta']);
});

test.tags('muk_web_tree', 'desktop');
test('treelist carries the list view styles', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    expect('.o_view_controller').toHaveClass('o_list_view');
    expect('thead th[data-name=name]').toHaveClass('mk_treelist_header');
});

test.tags('muk_web_tree', 'desktop');
test('pages the children of a parent with its own pager', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist limit="1"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha One']);
    expect('.o_data_row:eq(0) .mk_treelist_pager .o_pager_value').toHaveText('1');
    expect('.o_data_row:eq(0) .mk_treelist_pager .o_pager_limit').toHaveText('2');
    await contains('.o_data_row:eq(0) .mk_treelist_pager .o_pager_next').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha Two']);
    expect('.o_data_row:eq(0) .mk_treelist_pager .o_pager_value').toHaveText('2');
    expect('.o_pager_value:not(.mk_treelist_pager *)').toHaveText('1');
});

test.tags('muk_web_tree', 'desktop');
test('selecting the whole domain counts every record', async () => {
    await mountView({ type: 'treelist', resModel: 'category', arch: TREE_ARCH });
    await contains('thead .o_list_record_selector input').click();
    expect('.o_select_domain').toHaveText('Select all');
    await contains('.o_select_domain').click();
    expect('.o_selection_box').toHaveText(/All 5 selected/);
});

test.tags('muk_web_tree', 'desktop');
test('search expansions are not remembered', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_leaf: 1 },
    });
    expect(rowNames()).toEqual(['Alpha', 'Alpha Two', 'Alpha Two Leaf']);
    expect(JSON.parse(browser.localStorage.getItem('mk_treelist,category,0'))).toEqual(
        [],
    );
});

test.tags('muk_web_tree', 'desktop');
test('context rows cannot be selected', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_leaf: 1 },
    });
    expect('.mk_treelist_context .o_list_record_selector input:disabled').toHaveCount(
        2,
    );
    await contains('thead .o_list_record_selector input').click();
    expect('.o_data_row_selected').toHaveCount(1);
    expect('.o_data_row_selected td[name=name]').toHaveText('Alpha Two Leaf');
    expect('thead .o_list_record_selector input').toBeChecked();
});

test.tags('muk_web_tree', 'desktop');
test('selecting the whole search skips the context rows', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_leaf: 1 },
    });
    await contains('thead .o_list_record_selector input').click();
    await contains('.o_select_domain').click();
    expect('.o_selection_box').toHaveText(/All 1 selected/);
    expect('.o_data_row_selected').toHaveCount(1);
});

test.tags('muk_web_tree', 'desktop');
test('range selection skips the context rows', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_one_and_leaf: 1 },
    });
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Alpha Two Leaf']);
    await contains('.o_data_row .o_list_record_selector input:enabled:eq(0)').click();
    await contains('.o_data_row .o_list_record_selector input:enabled:eq(1)').click({
        shiftKey: true,
    });
    expect(queryAllTexts('.o_data_row_selected td[name=name]')).toEqual([
        'Alpha One',
        'Alpha Two Leaf',
    ]);
});

test.tags('muk_web_tree', 'desktop');
test('children start at their first page on any root page', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist limit="1" default_order="name desc"><field name="name"/></treelist>',
    });
    expect(rowNames()).toEqual(['Beta']);
    await contains('.o_pager_next').click();
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha Two']);
    expect('.o_data_row:eq(0) .mk_treelist_pager .o_pager_limit').toHaveText('2');
});

test.tags('muk_web_tree', 'desktop');
test('keyboard range selection skips the context rows', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: TREE_ARCH,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_one_and_leaf: 1 },
    });
    await contains('.o_data_row:eq(1) .o_list_record_selector input').click();
    await press(['shift', 'arrowdown']);
    await press(['shift', 'arrowdown']);
    await animationFrame();
    expect(queryAllTexts('.o_data_row_selected td[name=name]')).toEqual([
        'Alpha One',
        'Alpha Two Leaf',
    ]);
    expect('.mk_treelist_context.o_data_row_selected').toHaveCount(0);
});
