import { expect, test } from "@odoo/hoot";
import { mountView } from "@web/../tests/web_test_helpers";

import { defineProductModels, listArch } from "./helpers/product_model";

import "@muk_web_utils/views/fields/text_icons/text_icon";

defineProductModels();

test.tags("muk_web_utils");
test("text icon widget hides icon when value empty", async () => {
    await mountView({
        type: "list",
        resModel: "product",
        arch: listArch({
            body: `
                <field
                    name="description"
                    widget="text_icon"
                    nolabel="1"
                    options="{'icon': 'book'}"
                />
            `,
        }),
    });
    expect(".o_list_table tbody tr:nth-child(1) .fa-book").toHaveCount(1);
    expect(".o_list_table tbody tr:nth-child(2) .fa-book").toHaveCount(0);
});
