import { click } from '@odoo/hoot-dom';
import { expect, test } from '@odoo/hoot';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    contains,
    defineModels,
    fields,
    mockService,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';

import '@muk_product/views/list/product_list_view';
import '@muk_product/views/kanban/product_kanban_view';

class ProductTemplate extends models.Model {
    _name = 'product.template';
    _records = [
        { id: 1, name: 'Product 1' },
        { id: 2, name: 'Product 2' },
    ];
    name = fields.Char();
}

defineModels([ProductTemplate]);
defineMailModels();

const listArch = `
    <list js_class="product_search_list">
        <field name="name"/>
    </list>
`;

const kanbanArch = `
    <kanban js_class="product_search_kanban">
        <templates>
            <t t-name="card">
                <field name="name"/>
            </t>
        </templates>
    </kanban>
`;

function trackDoAction() {
    const calls = [];
    mockService('action', {
        doAction(action) {
            calls.push(action);
        },
    });
    return calls;
}

test.tags('muk_product', 'desktop');
test('product list exposes a search button opening the wizard', async () => {
    const calls = trackDoAction();
    await mountView({
        type: 'list',
        resModel: 'product.template',
        arch: listArch,
    });
    expect('.mk_button_product_search').toHaveCount(1);
    expect('.mk_button_product_search').toHaveText('Search');
    await click('.mk_button_product_search');
    expect(calls).toEqual(['muk_product.action_product_search']);
});

test.tags('muk_product', 'desktop');
test('product list keeps its records and its standard create button', async () => {
    await mountView({
        type: 'list',
        resModel: 'product.template',
        arch: listArch,
    });
    expect('.o_list_table tbody tr.o_data_row').toHaveCount(2);
    expect('.o_list_button_add').toHaveCount(1);
});

test.tags('muk_product', 'desktop');
test('product kanban exposes a search button opening the wizard', async () => {
    const calls = trackDoAction();
    await mountView({
        type: 'kanban',
        resModel: 'product.template',
        arch: kanbanArch,
    });
    expect('.mk_button_product_search').toHaveCount(1);
    expect('.mk_button_product_search').toHaveText('Search');
    await click('.mk_button_product_search');
    expect(calls).toEqual(['muk_product.action_product_search']);
});

test.tags('muk_product', 'desktop');
test('product kanban keeps its records and its standard create button', async () => {
    await mountView({
        type: 'kanban',
        resModel: 'product.template',
        arch: kanbanArch,
    });
    expect('.o_kanban_record:not(.o_kanban_ghost)').toHaveCount(2);
    expect('.o-kanban-button-new').toHaveCount(1);
});

test.tags('muk_product', 'mobile');
test('product list offers the search button in the mobile dropdown', async () => {
    const calls = trackDoAction();
    await mountView({
        type: 'list',
        resModel: 'product.template',
        arch: listArch,
    });
    await contains('.o_control_panel_main_buttons .dropdown-toggle').click();
    await contains('.dropdown-item.mk_button_product_search').click();
    expect(calls).toEqual(['muk_product.action_product_search']);
});

test.tags('muk_product', 'mobile');
test('product kanban offers the search button in the mobile dropdown', async () => {
    const calls = trackDoAction();
    await mountView({
        type: 'kanban',
        resModel: 'product.template',
        arch: kanbanArch,
    });
    await contains('.o_control_panel_main_buttons .dropdown-toggle').click();
    await contains('.dropdown-item.mk_button_product_search').click();
    expect(calls).toEqual(['muk_product.action_product_search']);
});
