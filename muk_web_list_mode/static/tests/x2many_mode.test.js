import { describe, expect, test } from '@odoo/hoot';
import { queryAll } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';

import { browser } from '@web/core/browser/browser';
import { user } from '@web/core/user';
import { session } from '@web/session';

import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

describe.current.tags('muk_web_list_mode', 'desktop');

class Order extends models.Model {
    _records = [{ id: 1, name: 'Order', line_ids: [1, 2] }];
    name = fields.Char();
    line_ids = fields.One2many({ relation: 'line', relation_field: 'order_id' });
}

class Line extends models.Model {
    _records = [
        { id: 1, name: 'Line 1', order_id: 1 },
        { id: 2, name: 'Line 2', order_id: 1 },
    ];
    name = fields.Char();
    order_id = fields.Many2one({ relation: 'order' });
    _views = { form: '<form><field name="name"/></form>' };
}

defineModels({ Order, Line });

onRpc('has_group', () => true);

/**
 * Mount the order form with the given list arch for its lines.
 * @param {string} list the ``<list>`` arch of the lines
 * @param {string} [fieldAttrs] extra attributes of the lines field
 */
async function mountOrder(list, fieldAttrs = '') {
    await mountView({
        type: 'form',
        resModel: 'order',
        resId: 1,
        arch: `<form><field name="line_ids" ${fieldAttrs}>${list}</field></form>`,
    });
}

const PLAIN = '<list><field name="name"/></list>';
const TOGGLE = '.o_field_x2many .mk_mode_toggle';
const ROW = '.o_field_x2many .o_data_row:eq(0) .o_data_cell';
const ADD = '.o_field_x2many .o_field_x2many_list_row_add button';

test('the toggle starts in the mode of the arch', async () => {
    await mountOrder(PLAIN);
    expect(TOGGLE).toHaveAttribute('data-mode', 'read');
    await contains(ROW).click();
    expect('.modal .o_form_view').toHaveCount(1);
});

test('edit mode edits rows and adds lines inline at the arch position', async () => {
    await mountOrder('<list editable="top"><field name="name"/></list>');
    expect(TOGGLE).toHaveAttribute('data-mode', 'edit');
    await contains(TOGGLE).click();
    await contains(ROW).click();
    expect('.modal .o_form_view').toHaveCount(1);
    await contains('.modal .o_form_button_cancel').click();
    await contains(TOGGLE).click();
    await contains(ROW).click();
    expect('.o_field_x2many .o_selected_row').toHaveCount(1);
    await contains(ADD).click();
    await animationFrame();
    expect('.o_field_x2many .o_data_row:eq(0)').toHaveClass('o_selected_row');
    expect('.modal').toHaveCount(0);
});

test('a plain list edits at the bottom and adds lines in a dialog in read mode', async () => {
    await mountOrder(PLAIN);
    await contains(ADD).click();
    expect('.modal .o_form_view').toHaveCount(1);
    await contains('.modal .o_form_button_cancel').click();
    await contains(TOGGLE).click();
    await contains(ADD).click();
    await animationFrame();
    expect('.o_field_x2many .o_data_row:eq(2)').toHaveClass('o_selected_row');
});

test('a list without actions column gets one for the toggle in every row', async () => {
    await mountOrder('<list delete="0"><field name="name"/></list>');
    expect('.o_field_x2many thead .o_list_actions_header .mk_mode_toggle').toHaveCount(
        1,
    );
    for (const row of queryAll(
        '.o_field_x2many .o_data_row, .o_field_x2many tfoot tr',
    )) {
        expect(row.children.length).toBe(2);
    }
});

test('the chosen mode is stored and restored per model and field', async () => {
    patchWithCleanup(user, { userId: 77 });
    const key = `mk_list_mode,${session.db},77,order,line_ids`;
    browser.localStorage.setItem(key, 'edit');
    await mountOrder(PLAIN);
    expect(TOGGLE).toHaveAttribute('data-mode', 'edit');
    await contains(TOGGLE).click();
    expect(TOGGLE).toHaveAttribute('data-mode', 'read');
    expect(browser.localStorage.getItem(key)).toBe('read');
});

for (const [label, list, fieldAttrs] of [
    ['a readonly field', PLAIN, 'readonly="1"'],
    ['a list that forbids editing', '<list edit="0"><field name="name"/></list>', ''],
    ['a kanban', '<kanban><templates><t t-name="card"/></templates></kanban>', ''],
]) {
    test(`no toggle is offered for ${label}`, async () => {
        await mountOrder(list, fieldAttrs);
        expect('.o_field_x2many').toHaveCount(1);
        expect(TOGGLE).toHaveCount(0);
    });
}
