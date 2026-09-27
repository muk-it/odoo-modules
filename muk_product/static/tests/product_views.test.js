import { click } from '@odoo/hoot-dom';
import { expect, test } from '@odoo/hoot';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
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

for (const [type, arch, recordSelector, createSelector] of [
    ['list', listArch, '.o_data_row', '.o_list_button_add'],
    [
        'kanban',
        kanbanArch,
        '.o_kanban_record:not(.o_kanban_ghost)',
        '.o-kanban-button-new',
    ],
]) {
    test.tags('muk_product', 'desktop');
    test(`product ${type} adds a search button opening the wizard`, async () => {
        const calls = [];
        mockService('action', {
            doAction(action) {
                calls.push(action);
            },
        });
        await mountView({ type, resModel: 'product.template', arch });
        expect(recordSelector).toHaveCount(2);
        expect(createSelector).toHaveCount(1);
        await click('.mk_button_product_search');
        expect(calls).toEqual(['muk_product.action_product_search']);
    });
}
