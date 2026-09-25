import { expect, test } from '@odoo/hoot';
import { queryAllTexts } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    contains,
    mockService,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { browser } from '@web/core/browser/browser';

import { defineTreeModels, rowNames, SEARCH_ARCH } from './helpers/models';

defineTreeModels();

test.tags('muk_web_tree', 'desktop');
test('rollup columns show subtree totals', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: `
            <treelist>
                <field name="name"/>
                <field name="amount" sum="Total" rollup="1"/>
            </treelist>
        `,
    });
    expect(queryAllTexts('.o_data_row td[name=amount]')).toEqual(['10', '5']);
    expect('tfoot td.o_list_number').toHaveText('15');
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(queryAllTexts('.o_data_row td[name=amount]')).toEqual(['10', '2', '7', '5']);
    expect('tfoot td.o_list_number').toHaveText('15');
});

test.tags('muk_web_tree', 'desktop');
test('sum without rollup adds the own values of the visible rows', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: `
            <treelist>
                <field name="name"/>
                <field name="amount" sum="Total"/>
            </treelist>
        `,
    });
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(queryAllTexts('.o_data_row td[name=amount]')).toEqual(['1', '2', '3', '5']);
    expect('tfoot td.o_list_number').toHaveText('11');
});

test.tags('muk_web_tree', 'desktop');
test('adds a child inline under its parent', async () => {
    onRpc('category', 'web_save', ({ args }) => {
        expect.step(['web_save', args[1]]);
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist editable="bottom"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(0) .mk_treelist_add', { visible: false }).click();
    expect('.o_selected_row').toHaveAttribute('aria-level', '2');
    expect(rowNames().slice(0, 3)).toEqual(['Alpha', 'Alpha One', 'Alpha Two']);
    expect('.o_data_row:eq(3)').toHaveClass('o_selected_row');
    await contains('.o_selected_row td[name=name] input').edit('Alpha Three', {
        confirm: false,
    });
    await contains('.o_list_button_save').click();
    expect.verifySteps([['web_save', { name: 'Alpha Three', parent_id: 1 }]]);
});

test.tags('muk_web_tree', 'desktop');
test('adds a child in a form when the treelist is not editable', async () => {
    mockService('action', {
        doAction(action) {
            expect.step([action.res_model, action.context.default_parent_id]);
        },
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(1) .mk_treelist_add', { visible: false }).click();
    expect.verifySteps([['category', 5]]);
});

test.tags('muk_web_tree', 'desktop');
test('drops a row into another row to change its parent', async () => {
    onRpc('category', 'write', ({ args }) => {
        expect.step(['write', args[0], args[1]]);
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist draggable="1"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(1) .mk_treelist_handle', {
        visible: false,
    }).dragAndDrop('.o_data_row:eq(0)');
    await animationFrame();
    expect.verifySteps([['write', [5], { parent_id: 1 }]]);
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Beta']);
    expect('.o_data_row:eq(3)').toHaveAttribute('aria-level', '2');
});

test.tags('muk_web_tree', 'desktop');
test('rows cannot be dropped into their own descendants', async () => {
    onRpc('category', 'write', () => {
        expect.step('write');
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist draggable="1"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    await contains('.o_data_row:eq(0) .mk_treelist_handle', {
        visible: false,
    }).dragAndDrop('.o_data_row:eq(1)');
    await animationFrame();
    expect.verifySteps([]);
});

test.tags('muk_web_tree', 'desktop');
test('new adds a root row in an editable treelist', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist editable="bottom"><field name="name"/></treelist>',
    });
    await contains('.o_control_panel_main_buttons .o_list_button_add').click();
    expect('.o_selected_row').toHaveAttribute('aria-level', '1');
    await contains('.o_selected_row td[name=name] input').edit('Gamma');
    await contains('.o_list_button_save').click();
    expect(rowNames().slice(0, 3)).toEqual(['Alpha', 'Beta', 'Gamma']);
});

test.tags('muk_web_tree', 'desktop');
test('discarding a new child restores its parent', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist editable="bottom"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(1) .mk_treelist_add', { visible: false }).click();
    expect('.o_data_row:eq(1)').toHaveAttribute('aria-expanded', 'true');
    await contains('.o_list_button_discard').click();
    expect(rowNames()).toEqual(['Alpha', 'Beta']);
    expect('.o_data_row:eq(1) .mk_treelist_toggle').toHaveCount(0);
    expect('.o_pager_value').toHaveText('1-2');
});

test.tags('muk_web_tree', 'desktop');
test('rollup cells explain their total', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: `
            <treelist>
                <field name="name"/>
                <field name="amount" sum="Total" rollup="1"/>
            </treelist>
        `,
    });
    expect('.o_data_row:eq(0) td[name=amount]').toHaveClass('mk_treelist_rollup');
    expect('.o_data_row:eq(0) td[name=amount]').toHaveAttribute(
        'title',
        'Total including the children',
    );
    expect('.o_data_row:eq(1) td[name=amount]').not.toHaveClass('mk_treelist_rollup');
});

test.tags('muk_web_tree', 'desktop');
test('footer sums skip the context rows of a search', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: `
            <treelist>
                <field name="name"/>
                <field name="amount" sum="Total"/>
            </treelist>
        `,
        searchViewArch: SEARCH_ARCH,
        context: { search_default_leaf: 1 },
    });
    expect('tfoot td.o_list_number').toHaveText('4');
});

test.tags('muk_web_tree', 'desktop');
test('confirming a new child adds its next sibling', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist editable="bottom"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(1) .mk_treelist_add', { visible: false }).click();
    await contains('.o_selected_row td[name=name] input').edit('Beta One');
    expect('.o_selected_row').toHaveAttribute('aria-level', '2');
    expect(rowNames().slice(0, 3)).toEqual(['Alpha', 'Beta', 'Beta One']);
});

test.tags('muk_web_tree', 'desktop');
test('a first child keeps its parent expanded', async () => {
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist editable="bottom"><field name="name"/></treelist>',
    });
    await contains('.o_data_row:eq(1) .mk_treelist_add', { visible: false }).click();
    expect(JSON.parse(browser.localStorage.getItem('mk_treelist,category,0'))).toEqual([
        5,
    ]);
});

test.tags('muk_web_tree', 'desktop');
test('a handle field orders the rows among their siblings', async () => {
    onRpc('category', 'web_resequence', ({ args }) => {
        expect.step(['web_resequence', args[0]]);
    });
    onRpc('category', 'write', () => {
        expect.step('write');
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: '<treelist><field name="sequence" widget="handle"/><field name="name"/></treelist>',
    });
    expect('.o_handle_cell').toHaveCount(0);
    expect('.o_data_row:eq(0) .mk_treelist_cell').toHaveAttribute('name', 'name');
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Alpha Two', 'Beta']);
    await contains('.o_data_row:eq(2) .mk_treelist_handle', {
        visible: false,
    }).dragAndDrop('.o_data_row:eq(1)', { position: { y: 2 }, relative: true });
    await animationFrame();
    expect.verifySteps([['web_resequence', [3, 2]]]);
    expect(rowNames()).toEqual(['Alpha', 'Alpha Two', 'Alpha One', 'Beta']);
    await contains('.o_data_row:eq(3) .mk_treelist_handle', {
        visible: false,
    }).dragAndDrop('.o_data_row:eq(1)', { position: { y: 2 }, relative: true });
    await animationFrame();
    expect.verifySteps([]);
});

test.tags('muk_web_tree', 'desktop');
test('a row dropped next to another parent row moves there in order', async () => {
    onRpc('category', 'web_resequence', ({ args }) => {
        expect.step(['web_resequence', args[0]]);
    });
    onRpc('category', 'write', ({ args }) => {
        expect.step(['write', args[0], args[1]]);
    });
    await mountView({
        type: 'treelist',
        resModel: 'category',
        arch: `
            <treelist draggable="1">
                <field name="sequence" widget="handle"/>
                <field name="name"/>
            </treelist>`,
    });
    await contains('.o_data_row:eq(0) .mk_treelist_toggle').click();
    await contains('.o_data_row:eq(3) .mk_treelist_handle', {
        visible: false,
    }).dragAndDrop('.o_data_row:eq(2)', { position: { y: 2 }, relative: true });
    await animationFrame();
    expect.verifySteps([
        ['write', [5], { parent_id: 1 }],
        ['web_resequence', [2, 5, 3]],
    ]);
    expect(rowNames()).toEqual(['Alpha', 'Alpha One', 'Beta', 'Alpha Two']);
});
