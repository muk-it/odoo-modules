import { describe, expect, test } from '@odoo/hoot';
import { queryOne } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';

import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';

import '@muk_web_utils/views/fields/module_link/module_link';

describe.current.tags('muk_web_utils');

class ToggleModel extends models.Model {
    _name = 'muk_web_utils.toggle_model';
    module_muk_toggle_a = fields.Boolean();
    _records = [{ id: 1, module_muk_toggle_a: false }];
}

class IrModuleModule extends models.Model {
    _name = 'ir.module.module';
    name = fields.Char();
    _records = [{ id: 1, name: 'muk_toggle_a' }];
}

defineModels([ToggleModel, IrModuleModule]);

const ARCH = `
    <form>
        <field name="module_muk_toggle_a" widget="module_link"/>
    </form>`;

// ----------------------------------------------------------
// Tests

test('ticking the checkbox writes the field back to the record', async () => {
    onRpc('web_save', ({ args }) => {
        expect.step(`web_save:${args[1].module_muk_toggle_a}`);
    });
    await mountView({
        resModel: 'muk_web_utils.toggle_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    const checkbox = queryOne('[name="module_muk_toggle_a"] input[type="checkbox"]');
    expect(checkbox.checked).toBe(false);
    await contains(checkbox).click();
    await animationFrame();
    expect(
        queryOne('[name="module_muk_toggle_a"] input[type="checkbox"]').checked,
    ).toBe(true);
    await contains('.o_form_button_save').click();
    await animationFrame();
    expect.verifySteps(['web_save:true']);
});

test('the checkbox mirrors a value changed on the record', async () => {
    await mountView({
        resModel: 'muk_web_utils.toggle_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    await contains('[name="module_muk_toggle_a"] input[type="checkbox"]').click();
    await animationFrame();
    await contains('.o_form_button_cancel').click();
    await animationFrame();
    expect(
        queryOne('[name="module_muk_toggle_a"] input[type="checkbox"]').checked,
    ).toBe(false);
});
