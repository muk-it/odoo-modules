import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';

import '@muk_web_utils/views/fields/x2many/x2many';

describe.current.tags('muk_web_utils');

class Parent extends models.Model {
    _name = 'muk_web_utils.parent';
    name = fields.Char();
    line_ids = fields.One2many({
        relation: 'muk_web_utils.line',
        relation_field: 'parent_id',
    });
    _records = [{ id: 1, name: 'Parent', line_ids: [1, 2] }];
}

class Line extends models.Model {
    _name = 'muk_web_utils.line';
    name = fields.Char();
    parent_id = fields.Many2one({ relation: 'muk_web_utils.parent' });
    _records = [
        { id: 1, name: 'Line 1', parent_id: 1 },
        { id: 2, name: 'Line 2', parent_id: 1 },
    ];
}

defineModels([Parent, Line]);

const notebookArch = (options) => `
    <form>
        <notebook>
            <page string="Lines">
                <field name="line_ids"${options}>
                    <list><field name="name"/></list>
                    <form><field name="name"/></form>
                </field>
            </page>
            <page string="Other">
                <field name="name"/>
            </page>
        </notebook>
    </form>`;

test('rows of a plain x2many list open a record dialog', async () => {
    await mountView({
        type: 'form',
        resModel: 'muk_web_utils.parent',
        resId: 1,
        arch: notebookArch(''),
    });
    expect('.o_field_x2many_list .o_data_row').toHaveCount(2);
    await contains('.o_field_x2many_list .o_data_row:eq(0) .o_data_cell').click();
    expect('.modal').toHaveCount(1);
});

test('no_open prevents opening a record from the x2many list', async () => {
    await mountView({
        type: 'form',
        resModel: 'muk_web_utils.parent',
        resId: 1,
        arch: notebookArch(' options="{\'no_open\': 1}"'),
    });
    await contains('.o_field_x2many_list .o_data_row:eq(0) .o_data_cell').click();
    expect('.modal').toHaveCount(0);
});

test('no_open survives the field being re-created by a notebook page switch', async () => {
    await mountView({
        type: 'form',
        resModel: 'muk_web_utils.parent',
        resId: 1,
        arch: notebookArch(' options="{\'no_open\': 1}"'),
    });
    await contains('.o_field_x2many_list .o_data_row:eq(0) .o_data_cell').click();
    expect('.modal').toHaveCount(0);
    await contains('.o_notebook .nav-link:eq(1)').click();
    await animationFrame();
    expect('.o_field_x2many_list').toHaveCount(0);
    await contains('.o_notebook .nav-link:eq(0)').click();
    await animationFrame();
    expect('.o_field_x2many_list .o_data_row').toHaveCount(2);
    await contains('.o_field_x2many_list .o_data_row:eq(0) .o_data_cell').click();
    expect('.modal').toHaveCount(0);
});
