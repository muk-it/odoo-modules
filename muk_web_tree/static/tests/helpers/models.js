import { queryAll, queryAllAttributes } from '@odoo/hoot-dom';
import { defineModels, fields, models, onRpc } from '@web/../tests/web_test_helpers';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';

function subtreeIds(recordIds, parentOf, rootId) {
    const ids = [rootId];
    for (let index = 0; index < ids.length; index++) {
        ids.push(...recordIds.filter((id) => parentOf(id) === ids[index]));
    }
    return ids;
}

function webTreeRead({ model, kwargs }) {
    const Model = this.env[model];
    const parentField = kwargs.parent_field;
    const value = (id, name) => Model.read([id], [name])[0]?.[name];
    const exists = (id) => Model.search([['id', '=', id]]).length > 0;
    const parentOf = (id) => {
        const parent = value(id, parentField);
        return (Array.isArray(parent) ? parent[0] : parent?.id || parent) || false;
    };
    const matchIds = new Set(Model.search(kwargs.domain));
    const contextIds = new Set();
    let frontier = !kwargs.search
        ? []
        : [...matchIds].map(parentOf).filter((id) => id && !matchIds.has(id));
    while (frontier.length) {
        const next = [];
        for (const id of frontier) {
            if (!exists(id) || matchIds.has(id) || contextIds.has(id)) {
                continue;
            }
            contextIds.add(id);
            if (parentOf(id)) {
                next.push(parentOf(id));
            }
        }
        frontier = next;
    }
    const visibleIds = new Set([...matchIds, ...contextIds]);
    const orderedIds = Model.search(
        [['id', 'in', [...visibleIds]]],
        0,
        false,
        kwargs.order,
    );
    const children = (id) => orderedIds.filter((childId) => parentOf(childId) === id);
    const roots = kwargs.parent_id
        ? orderedIds.filter((id) => parentOf(id) === kwargs.parent_id)
        : orderedIds.filter((id) => !visibleIds.has(parentOf(id)));
    const offset = kwargs.offset || 0;
    const page = roots.slice(offset, kwargs.limit ? offset + kwargs.limit : undefined);
    const expanded = new Set(kwargs.expanded_ids || []);
    if (kwargs.expand_context) {
        for (const id of contextIds) {
            expanded.add(id);
            expanded.add(parentOf(id));
        }
    }
    const rows = [];
    const visit = (id, level) => {
        const allChildIds = children(id);
        const childOffset = kwargs.child_offsets?.[id] || 0;
        const childIds = allChildIds.slice(
            childOffset,
            kwargs.limit ? childOffset + kwargs.limit : undefined,
        );
        const isExpanded =
            Boolean(childIds.length) && (kwargs.expand_all || expanded.has(id));
        const rollups = {};
        if (allChildIds.length) {
            const ids = subtreeIds([...visibleIds], parentOf, id).filter((subId) =>
                matchIds.has(subId),
            );
            for (const name of kwargs.rollup_fields || []) {
                rollups[name] = ids.reduce(
                    (sum, subId) => sum + (value(subId, name) || 0),
                    0,
                );
            }
        }
        rows.push({
            id,
            __tree__: {
                level,
                count: allChildIds.length,
                offset: isExpanded ? childOffset : 0,
                context: contextIds.has(id),
                expanded: isExpanded,
                rollups,
            },
        });
        if (isExpanded) {
            for (const childId of childIds) {
                visit(childId, level + 1);
            }
        }
    };
    for (const id of page) {
        visit(id, 0);
    }
    const values = Model.web_read(
        rows.map((row) => row.id),
        kwargs.specification,
    );
    return {
        length: roots.length,
        records: rows.map((row) => ({
            ...values.find((value) => value.id === row.id),
            __tree__: row.__tree__,
        })),
    };
}

export class Category extends models.Model {
    _name = 'category';
    _order = 'name';
    _records = [
        {
            id: 1,
            name: 'Alpha',
            parent_id: false,
            amount: 1,
            group_key: 'A',
            sequence: 1,
        },
        {
            id: 2,
            name: 'Alpha One',
            parent_id: 1,
            amount: 2,
            group_key: 'A',
            sequence: 1,
        },
        {
            id: 3,
            name: 'Alpha Two',
            parent_id: 1,
            amount: 3,
            group_key: 'A',
            sequence: 2,
        },
        {
            id: 4,
            name: 'Alpha Two Leaf',
            parent_id: 3,
            amount: 4,
            group_key: 'B',
            sequence: 1,
        },
        {
            id: 5,
            name: 'Beta',
            parent_id: false,
            amount: 5,
            group_key: 'A',
            sequence: 2,
        },
    ];
    name = fields.Char();
    sequence = fields.Integer();
    amount = fields.Integer();
    group_key = fields.Char();
    parent_id = fields.Many2one({ relation: 'category' });
}

export function defineTreeModels() {
    defineMailModels();
    defineModels({ Category });
    onRpc('has_group', () => true);
    onRpc('web_tree_read', webTreeRead);
    onRpc('web_tree_search_count', function ({ model, kwargs }) {
        const ids = this.env[model].search(kwargs.domain);
        return this.env[model].search_count([
            ['id', 'in', ids],
            '|',
            [kwargs.parent_field, '=', false],
            [kwargs.parent_field, 'not in', ids],
        ]);
    });
}

export const SEARCH_ARCH = `
    <search>
        <filter name="leaf" string="Leaf" domain="[('name', '=', 'Alpha Two Leaf')]"/>
        <filter
            name="one_and_leaf"
            string="One and Leaf"
            domain="[('name', 'in', ['Alpha One', 'Alpha Two Leaf'])]"
        />
    </search>
`;

export const TREE_ARCH = `
    <treelist>
        <field name="name"/>
        <field name="amount"/>
    </treelist>
`;

export function rowNames() {
    return queryAll('.o_data_row td[name=name]').map((cell) => {
        const text = cell.cloneNode(true);
        text.querySelector('.mk_treelist_pager')?.remove();
        return text.textContent.trim();
    });
}

export function rowLevels() {
    return queryAllAttributes('.o_data_row', 'aria-level');
}
