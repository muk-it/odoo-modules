import { expect, test } from '@odoo/hoot';
import {
    contains,
    defineModels,
    defineWebModels,
    fields,
    models,
    mountView,
    onRpc,
    toggleMenuItem,
    toggleSearchBarMenu,
} from '@web/../tests/web_test_helpers';

import '@muk_web_group/search/collapse_all/collapse_all';
import '@muk_web_group/search/expand_all/expand_all';

class Category extends models.Model {
    _records = [
        { id: 1, name: 'Cat A' },
        { id: 2, name: 'Cat B' },
    ];
    name = fields.Char();
}

class Product extends models.Model {
    _records = [
        { id: 1, name: 'A-1', category_id: 1, stage: 'new' },
        { id: 2, name: 'A-2', category_id: 1, stage: 'done' },
        { id: 3, name: 'B-1', category_id: 2, stage: 'new' },
    ];
    name = fields.Char();
    stage = fields.Char();
    category_id = fields.Many2one({ relation: 'category' });
}

defineWebModels();
defineModels({ Category, Product });
onRpc('has_group', () => true);

const LIST_ARCH = `
    <list>
        <field name="name"/>
        <field name="category_id"/>
    </list>
`;

const KANBAN_ARCH = `
    <kanban>
        <templates>
            <t t-name="card">
                <field name="name"/>
            </t>
        </templates>
    </kanban>
`;

function mountList(groupBy) {
    return mountView({ type: 'list', resModel: 'product', arch: LIST_ARCH, groupBy });
}

function mountKanban() {
    return mountView({
        type: 'kanban',
        resModel: 'product',
        arch: KANBAN_ARCH,
        groupBy: ['category_id'],
    });
}

async function clickCogItem(selector) {
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    await contains(selector).click();
}

function cogMenuShape() {
    return [...document.querySelector('.o-dropdown--menu').children].map((element) =>
        element.classList.contains('dropdown-divider')
            ? '---'
            : element.textContent.trim(),
    );
}

for (const [groupBy, headers] of [
    [['category_id'], 2],
    [['category_id', 'stage'], 5],
]) {
    test.tags('muk_web_group');
    test(`expand all opens ${groupBy.length} group level(s) with one request each`, async () => {
        const requests = [];
        onRpc('product', '*', ({ method }) => {
            requests.push(method);
        });
        await mountList(groupBy);
        expect('tbody tr.o_data_row').toHaveCount(0);
        requests.length = 0;
        await clickCogItem('.mk_expand_all_menu');
        expect('tbody tr.o_data_row').toHaveCount(3);
        expect('.o_group_header').toHaveCount(headers);
        expect(requests).toEqual(groupBy.map(() => 'web_read_group'));
    });
}

test.tags('muk_web_group');
test('collapse all folds nested groups back to the top level', async () => {
    await mountList(['category_id', 'stage']);
    await clickCogItem('.mk_expand_all_menu');
    expect('.o_group_header').toHaveCount(5);
    await clickCogItem('.mk_collapse_all_menu');
    expect('.o_group_header').toHaveCount(2);
    expect('tbody tr.o_data_row').toHaveCount(0);
});

test.tags('muk_web_group');
test('collapse all leaves an already folded group folded', async () => {
    await mountList(['category_id']);
    await contains('.o_group_header:first').click();
    expect('tbody tr.o_data_row').toHaveCount(2);
    await clickCogItem('.mk_collapse_all_menu');
    expect('tbody tr.o_data_row').toHaveCount(0);
});

test.tags('muk_web_group', 'desktop');
test('collapse all and expand all fold and unfold kanban columns', async () => {
    await mountKanban();
    expect('.o_kanban_record').toHaveCount(3);
    await clickCogItem('.mk_collapse_all_menu');
    expect('.o_kanban_group.o_column_folded').toHaveCount(2);
    expect('.o_kanban_record').toHaveCount(0);
    await clickCogItem('.mk_expand_all_menu');
    expect('.o_kanban_group.o_column_folded').toHaveCount(0);
    expect('.o_kanban_record').toHaveCount(3);
});

test.tags('muk_web_group');
test('the entries follow the grouping of an open list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: LIST_ARCH,
        searchViewArch: `
            <search>
                <filter string="Category" name="group_category" context="{'group_by': 'category_id'}"/>
            </search>
        `,
    });
    const toggleCog = () => contains('.o_cp_action_menus .dropdown-toggle').click();
    for (const count of [0, 1, 0]) {
        await toggleCog();
        expect('.mk_expand_all_menu').toHaveCount(count);
        expect('.mk_collapse_all_menu').toHaveCount(count);
        await toggleCog();
        await toggleSearchBarMenu();
        await toggleMenuItem('Category');
    }
});

test.tags('muk_web_group');
test('the two entries sit together in their own group of the cog menu', async () => {
    await mountList(['category_id']);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    const shape = cogMenuShape();
    expect(shape.indexOf('Expand All')).toBe(shape.indexOf('Collapse All') - 1);
    expect(shape[shape.indexOf('Expand All') - 1]).toBe('---');
});

test.tags('muk_web_group');
test('the cog menu is left with no empty group when the entries are hidden', async () => {
    await mountList([]);
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    const shape = cogMenuShape();
    expect(shape).not.toInclude('Expand All');
    expect(
        shape.some((entry, index) => entry === '---' && shape[index + 1] === '---'),
    ).toBe(false);
    expect(shape.at(-1)).not.toBe('---');
});

test.tags('muk_web_group', 'mobile');
test('a small-screen kanban offers neither entry', async () => {
    await mountKanban();
    await contains('.o_cp_action_menus .dropdown-toggle').click();
    expect('.o-dropdown--menu').toHaveCount(1);
    expect('.mk_collapse_all_menu').toHaveCount(0);
    expect('.mk_expand_all_menu').toHaveCount(0);
});

test.tags('muk_web_group', 'mobile');
test('a small-screen list still offers both entries', async () => {
    await mountList(['category_id']);
    await clickCogItem('.mk_expand_all_menu');
    expect('tbody tr.o_data_row').toHaveCount(3);
    await clickCogItem('.mk_collapse_all_menu');
    expect('tbody tr.o_data_row').toHaveCount(0);
});
