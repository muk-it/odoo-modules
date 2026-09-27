import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';

import { browser } from '@web/core/browser/browser';
import { UIPlugin } from '@web/core/ui/ui_plugin';
import { user } from '@web/core/user';
import { session } from '@web/session';

import {
    contains,
    defineModels,
    fields,
    getService,
    models,
    mountView,
    mountViewInDialog,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

describe.current.tags('muk_web_list_mode', 'desktop');

class Product extends models.Model {
    _records = [
        { id: 1, name: 'Test 1' },
        { id: 2, name: 'Test 2' },
    ];
    name = fields.Char();
}

defineModels({ Product });

onRpc('has_group', () => true);

const LIST_ARCH = '<list><field name="name"/></list>';
const READ = '.mk_mode_switch button[data-mode="read"]';
const EDIT = '.mk_mode_switch button[data-mode="edit"]';

/**
 * Record every list-mode key written to local storage.
 * @returns {Array} the collected ``[key, value]`` pairs
 */
function trackModeStorage() {
    const writes = [];
    patchWithCleanup(browser.localStorage, {
        setItem(key, value) {
            if (key.startsWith('mk_list_mode')) {
                writes.push([key, value]);
            }
            return super.setItem(key, value);
        },
    });
    return writes;
}

test('the switch offers both modes and marks the current one', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: LIST_ARCH });
    expect('.mk_mode_switch button').toHaveCount(2);
    expect(READ).toHaveClass('active');
    expect(EDIT).not.toHaveClass('active');
});

test('switching modes toggles inline editing at the arch position', async () => {
    const writes = trackModeStorage();
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list editable="top"><field name="name"/></list>',
    });
    expect(EDIT).toHaveClass('active');
    await contains(READ).click();
    expect(READ).toHaveClass('active');
    await contains('.o_data_row:eq(0) .o_data_cell').click();
    expect('.o_selected_row').toHaveCount(0);
    await contains(EDIT).click();
    await contains('.o_list_button_add').click();
    await animationFrame();
    expect('.o_data_row').toHaveCount(3);
    expect('.o_data_row:eq(0)').toHaveClass('o_selected_row');
    expect(writes).toHaveLength(0);
});

test('edit mode makes a plain list multi-editable', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: LIST_ARCH });
    await contains(EDIT).click();
    await contains('.o_data_row:eq(0) .o_list_record_selector input').click();
    await contains('.o_data_row:eq(1) .o_list_record_selector input').click();
    await contains('.o_data_row:eq(0) .o_data_cell').click();
    await contains('.o_selected_row .o_field_widget[name=name] input').edit('Both');
    await contains('.modal .btn-primary').click();
    expect('.o_data_row:eq(0) .o_data_cell').toHaveText('Both');
    expect('.o_data_row:eq(1) .o_data_cell').toHaveText('Both');
});

test('the chosen mode is stored per user, action and model', async () => {
    patchWithCleanup(user, { userId: 77 });
    const writes = trackModeStorage();
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: LIST_ARCH,
        config: { actionId: 42 },
    });
    await contains(EDIT).click();
    await contains(READ).click();
    expect(writes).toHaveLength(2);
    expect(writes[0][0]).toInclude(',77,42,product');
    expect(writes.map(([, mode]) => mode)).toEqual(['edit', 'read']);
});

test('the stored mode is restored for the action', async () => {
    patchWithCleanup(user, { userId: 77 });
    browser.localStorage.setItem(`mk_list_mode,${session.db},77,42,product`, 'edit');
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: LIST_ARCH,
        config: { actionId: 42 },
    });
    expect(EDIT).toHaveClass('active');
    await contains('.o_data_row:eq(0) .o_data_cell').click();
    expect('.o_selected_row').toHaveCount(1);
});

test('no switch is offered when editing is disabled on the list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list edit="0"><field name="name"/></list>',
    });
    expect('.mk_mode_switch').toHaveCount(0);
});

test('no switch is offered in a dialog', async () => {
    await mountViewInDialog({ type: 'list', resModel: 'product', arch: LIST_ARCH });
    expect('.modal .o_data_row').toHaveCount(2);
    expect('.modal .mk_mode_switch').toHaveCount(0);
});

test('the switch is hidden on small screens', async () => {
    await mountView({ type: 'list', resModel: 'product', arch: LIST_ARCH });
    expect('.mk_mode_switch').toHaveCount(1);
    getService(UIPlugin).isSmall.set(true);
    await animationFrame();
    expect('.mk_mode_switch').toHaveCount(0);
});
