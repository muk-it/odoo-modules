import { describe, expect, test } from '@odoo/hoot';
import { queryOne } from '@odoo/hoot-dom';

import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    webModels,
} from '@web/../tests/web_test_helpers';
import { user } from '@web/core/user';
import { patch } from '@web/core/utils/patch';

import {
    getColumnWidth,
    setColumnWidth,
} from '@muk_web_list_column/views/list/list_view_storage';

describe.current.tags('muk_web_list_column', 'desktop');

const { ResCompany, ResPartner, ResUsers } = webModels;

class Contact extends models.Model {
    _name = 'mk.contact';
    _records = [{ id: 1, name: 'Alice', ref: 'A-1', sequence: 1 }];
    name = fields.Char();
    ref = fields.Char();
    sequence = fields.Integer();
}

defineModels({ Contact, ResCompany, ResPartner, ResUsers });

/**
 * Mount a contact list view with the given arch.
 * @param {string} arch the list arch
 * @returns {Promise<void>}
 */
async function mountList(arch) {
    await mountView({ type: 'list', resModel: 'mk.contact', arch });
}

/**
 * Return the rendered width of the header cell of a column.
 * @param {string} name the column name
 * @returns {number}
 */
function headerWidth(name) {
    return queryOne(`.o_list_table thead th[data-name="${name}"]`).offsetWidth;
}

/**
 * Return the horizontal padding of a header cell.
 * @param {HTMLElement} th the header cell
 * @returns {number}
 */
function padding(th) {
    const { paddingLeft, paddingRight } = getComputedStyle(th);
    return parseFloat(paddingLeft) + parseFloat(paddingRight);
}

for (const [label, arch] of [
    ['a field column', '<list><field name="name"/><field name="ref"/></list>'],
    [
        'a column group',
        '<list><column name="name" string="Contact"><field name="name"/>' +
            '<field name="ref"/></column><field name="sequence"/></list>',
    ],
]) {
    test(`dragging ${label} stores its width`, async () => {
        await mountList(arch);
        expect(getColumnWidth('mk.contact', 'name')).toBe(null);
        await contains('.o_list_table th:eq(1) .o_resize', {
            visible: false,
        }).dragAndDrop('.o_list_table th:eq(2)');
        const th = queryOne('.o_list_table th:eq(1)');
        const stored = parseFloat(getColumnWidth('mk.contact', 'name'));
        expect(stored + padding(th)).toBeWithin(th.offsetWidth - 2, th.offsetWidth);
    });
}

for (const [label, field] of [
    ['without an arch width', '<field name="name"/>'],
    ['over an arch width', '<field name="name" width="60px"/>'],
]) {
    test(`a stored width is applied ${label}`, async () => {
        setColumnWidth('mk.contact', 'name', '400px');
        await mountList(`<list>${field}<field name="ref"/></list>`);
        const th = queryOne('.o_list_table thead th[data-name="name"]');
        expect(th.offsetWidth).toBe(Math.floor(400 + padding(th)));
    });
}

test('a width stored by another user is not applied', async () => {
    const unpatch = patch(user, { userId: user.userId + 1 });
    setColumnWidth('mk.contact', 'name', '400px');
    unpatch();
    await mountList(
        '<list><field name="name" width="60px"/><field name="ref"/></list>',
    );
    expect(headerWidth('name')).toBeLessThan(100);
});

test('an unlabelled column ignores a stored width', async () => {
    setColumnWidth('mk.contact', 'sequence', '400px');
    await mountList(
        '<list><field name="sequence" nolabel="1"/><field name="name"/></list>',
    );
    expect(queryOne('.o_list_table th:eq(1)').offsetWidth).toBeLessThan(100);
});

test('double-clicking a handle forgets every stored width at once', async () => {
    await mountList('<list><field name="name"/><field name="ref"/></list>');
    const automatic = headerWidth('name');
    setColumnWidth('mk.contact', 'name', '400px');
    setColumnWidth('mk.contact', 'ref', '300px');
    await mountList('<list><field name="name"/><field name="ref"/></list>');
    await contains('.o_list_table:last th:eq(1) .o_resize', {
        visible: false,
    }).dblclick();
    expect(getColumnWidth('mk.contact', 'name')).toBe(null);
    expect(getColumnWidth('mk.contact', 'ref')).toBe(null);
    expect(queryOne('.o_list_table:last thead th[data-name="name"]').offsetWidth).toBe(
        automatic,
    );
});
