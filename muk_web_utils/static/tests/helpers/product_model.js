import { defineModels, defineWebModels, fields, models } from "@web/../tests/web_test_helpers";

let areModelsDefined = false;

export class Product extends models.Model {
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

export function defineProductModels() {
    if (areModelsDefined) {
        return;
    }
    areModelsDefined = true;

    defineWebModels();
    defineModels({ Product });
}

export const listArch = ({ body }) => `
    <list>
        ${body}
    </list>
`;
