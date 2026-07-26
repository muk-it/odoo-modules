import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';

import { browser } from '@web/core/browser/browser';
import { user } from '@web/core/user';

import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import '@muk_web_list_mode/views/list/list_controller';

describe.current.tags('muk_web_list_mode');

class Product extends models.Model {
    _records = [
        { id: 1, name: 'Test 1' },
        { id: 2, name: 'Test 2' },
    ];
    name = fields.Char();
}

defineModels({ Product });

onRpc('has_group', () => true);

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

/**
 * Pretend a list mode was stored for every action.
 * @param {string} mode the mode to return from local storage
 */
function stubStoredMode(mode) {
    patchWithCleanup(browser.localStorage, {
        getItem(key) {
            if (key.startsWith('mk_list_mode')) {
                return mode;
            }
            return super.getItem(key);
        },
    });
}

test('renders both modes in the switch on an editable list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list><field name="name"/></list>',
    });
    expect('.mk_mode_switch').toHaveCount(1);
    expect('.mk_mode_switch button').toHaveCount(2);
    expect('.mk_mode_switch button[title="Open Form View"]').toHaveCount(1);
    expect('.mk_mode_switch button[title="Inline Edit Mode"]').toHaveCount(1);
});

test('the current mode is marked active', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list editable="bottom"><field name="name"/></list>',
    });
    expect('.mk_mode_switch button[title="Inline Edit Mode"]').toHaveClass('active');
    expect('.mk_mode_switch button[title="Open Form View"]').not.toHaveClass('active');
});

test('no switch is offered when editing is disabled on the list', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list edit="0"><field name="name"/></list>',
    });
    expect('.mk_mode_switch').toHaveCount(0);
});

test('the storage key is scoped to the user, action and model', async () => {
    patchWithCleanup(user, { userId: 77 });
    const writes = trackModeStorage();
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list><field name="name"/></list>',
        config: { actionId: 42 },
    });
    await contains('.mk_mode_switch button[title="Inline Edit Mode"]').click();
    expect(writes).toHaveLength(1);
    expect(writes[0][0]).toInclude(',77,42,product');
    expect(writes[0][0]).not.toInclude('undefined');
    expect(writes[0][1]).toBe('edit');
});

test('switching modes persists the chosen mode', async () => {
    const writes = trackModeStorage();
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list editable="bottom"><field name="name"/></list>',
        config: { actionId: 42 },
    });
    await contains('.mk_mode_switch button[title="Open Form View"]').click();
    expect(writes.at(-1)[1]).toBe('read');
    await contains('.mk_mode_switch button[title="Inline Edit Mode"]').click();
    expect(writes.at(-1)[1]).toBe('edit');
});

test('a stored edit mode makes a read-only list inline editable', async () => {
    stubStoredMode('edit');
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list><field name="name"/></list>',
        config: { actionId: 42 },
    });
    expect('.mk_mode_switch button[title="Inline Edit Mode"]').toHaveClass('active');
    await contains('.o_data_row:eq(0) .o_data_cell').click();
    expect('.o_selected_row').toHaveCount(1);
});

test('a stored read mode disables inline editing of an editable list', async () => {
    stubStoredMode('read');
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list editable="bottom"><field name="name"/></list>',
        config: { actionId: 42 },
    });
    expect('.mk_mode_switch button[title="Open Form View"]').toHaveClass('active');
    await contains('.o_data_row:eq(0) .o_data_cell').click();
    expect('.o_selected_row').toHaveCount(0);
});

test('the stored mode is ignored without an action id', async () => {
    stubStoredMode('edit');
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list><field name="name"/></list>',
    });
    expect('.mk_mode_switch button[title="Open Form View"]').toHaveClass('active');
});

test('the arch editable position survives a read to edit round trip', async () => {
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: '<list editable="top"><field name="name"/></list>',
        config: { actionId: 42 },
    });
    await contains('.mk_mode_switch button[title="Open Form View"]').click();
    await contains('.mk_mode_switch button[title="Inline Edit Mode"]').click();
    await contains('.o_list_button_add').click();
    await animationFrame();
    expect('.o_data_row').toHaveCount(3);
    expect('.o_data_row:eq(0)').toHaveClass('o_selected_row');
});
