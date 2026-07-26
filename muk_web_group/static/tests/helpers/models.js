import {
    defineModels,
    defineWebModels,
    fields,
    models,
    onRpc,
} from '@web/../tests/web_test_helpers';

export class Category extends models.Model {
    _records = [
        { id: 1, name: 'Cat A' },
        { id: 2, name: 'Cat B' },
    ];
    name = fields.Char();
}

export class Product extends models.Model {
    _records = [
        { id: 1, name: 'A-1', category_id: 1, stage: 'new' },
        { id: 2, name: 'A-2', category_id: 1, stage: 'done' },
        { id: 3, name: 'B-1', category_id: 2, stage: 'new' },
    ];
    name = fields.Char();
    stage = fields.Char();
    category_id = fields.Many2one({ relation: 'category' });
}

export function defineGroupModels() {
    defineWebModels();
    defineModels({ Category, Product });
    onRpc('has_group', () => true);
}

export const LIST_ARCH = `
    <list string="Products">
        <field name="name"/>
        <field name="category_id"/>
    </list>
`;

export const KANBAN_ARCH = `
    <kanban>
        <templates>
            <t t-name="card">
                <field name="name"/>
            </t>
        </templates>
    </kanban>
`;
