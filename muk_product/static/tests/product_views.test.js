import { click } from "@odoo/hoot-dom";
import { expect, test } from "@odoo/hoot";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
} from "@web/../tests/web_test_helpers";

import "@muk_product/views/list/product_list_view";
import "@muk_product/views/kanban/product/product_kanban_view";

class ProductTemplate extends models.Model {
    _name = "product.template";
    _records = [
        { id: 1, name: "Product 1" },
        { id: 2, name: "Product 2" },
    ];
    name = fields.Char();
}

defineModels([ProductTemplate]);
defineMailModels();

test.tags("muk_product");
test("product_search_list: Search button triggers action", async () => {
    let lastAction = null;
    mockService("action", {
        doAction(action) {
            lastAction = action;
        },
    });
    await mountView({
        type: "list",
        resModel: "product.template",
        arch: `
            <list js_class="product_search_list">
                <field name="name"/>
            </list>`,
    });
    expect(".mk_button_product_search").toHaveCount(1);
    await click(".mk_button_product_search");
    expect(lastAction).toBe("muk_product.action_product_search");
});

test.tags("muk_product");
test("product_search_kanban: Search button triggers action", async () => {
    let lastAction = null;
    mockService("action", {
        doAction(action) {
            lastAction = action;
        },
    });
    await mountView({
        type: "kanban",
        resModel: "product.template",
        arch: `
            <kanban js_class="product_search_kanban">
                <templates>
                    <t t-name="card">
                        <field name="name"/>
                    </t>
                </templates>
            </kanban>`,
    });
    expect(".mk_button_product_search").toHaveCount(1);
    await click(".mk_button_product_search");
    expect(lastAction).toBe("muk_product.action_product_search");
});
