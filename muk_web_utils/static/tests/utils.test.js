import { expect, test } from "@odoo/hoot";
import {
    defineModels,
    defineWebModels,
    fields,
    models,
    mountView,
} from "@web/../tests/web_test_helpers";

import "@muk_web_utils/views/fields/selection_icons/selection_icons";
import "@muk_web_utils/views/fields/text_icons/text_icon";

defineWebModels();

class Product extends models.Model {
    name = fields.Char();
    state = fields.Selection({
        selection: [
            ["ready", "Ready"],
            ["unknown", "Unknown"],
        ],
    });
    description = fields.Char();
    _records = [
        { id: 1, name: "Alpha", state: "ready", description: "Has value" },
        { id: 2, name: "Beta", state: "unknown", description: "" },
    ];
}

defineModels({ Product });

const listArch = ({ body }) => `
    <list>
        ${body}
    </list>
`;

test("list column with icon renders header icon", async () => {
    await mountView({
        type: "list",
        resModel: "product",
        arch: listArch({
            body: `
                <field name="name" string="Name" icon="fa fa-star text-info"/>
            `,
        }),
    });
    expect(".o_list_table thead th span.fa-star").toHaveCount(1);
    expect(".o_list_table thead th span.fa-star").toHaveClass("fa");
});

test("selection icons widget displays mapped and default icons", async () => {
    await mountView({
        type: "list",
        resModel: "product",
        arch: listArch({
            body: `
                <field
                    name="state"
                    widget="selection_icons"
                    nolabel="1"
                    options="{'icons': {'ready': 'check'}, 'defaultIcon': 'question'}"
                />
            `,
        }),
    });
    expect(".o_list_table tbody tr:nth-child(1) span.fa-check").toHaveCount(1);
    expect(".o_list_table tbody tr:nth-child(2) span.fa-question").toHaveCount(1);
});

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
});
