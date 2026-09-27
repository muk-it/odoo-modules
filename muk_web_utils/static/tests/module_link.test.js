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

class ModuleLinkModel extends models.Model {
    _name = 'muk_web_utils.module_link_model';
    module_muk_ai_schedule = fields.Boolean();
    module_muk_ai_skills = fields.Boolean();
    _records = [
        {
            id: 1,
            module_muk_ai_schedule: false,
            module_muk_ai_skills: false,
        },
    ];
}

class IrModuleModule extends models.Model {
    _name = 'ir.module.module';
    name = fields.Char();
    _records = [{ id: 1, name: 'muk_ai_schedule' }];
}

defineModels([ModuleLinkModel, IrModuleModule]);

/**
 * Mount a form showing the given module_link fields.
 * @param {string} fieldsXml the field nodes of the form
 * @returns {Promise<void>}
 */
async function mountForm(fieldsXml) {
    await mountView({
        resModel: 'muk_web_utils.module_link_model',
        resId: 1,
        type: 'form',
        arch: `<form>${fieldsXml}</form>`,
    });
}

// ----------------------------------------------------------
// Tests

test('an available module gets a checkbox, a missing one an Apps store link', async () => {
    await mountForm(`
        <field name="module_muk_ai_schedule" widget="module_link"/>
        <field name="module_muk_ai_skills" widget="module_link"/>`);
    expect('[name="module_muk_ai_schedule"] input[type="checkbox"]').toHaveCount(1);
    expect('[name="module_muk_ai_schedule"] a.o_module_link').toHaveCount(0);
    expect('[name="module_muk_ai_skills"] input[type="checkbox"]').toHaveCount(0);
    expect('[name="module_muk_ai_skills"] a.o_module_link').toHaveAttribute(
        'href',
        'https://apps.odoo.com/apps/modules/muk_ai_skills',
    );
});

test('the url option overrides the Apps store link', async () => {
    await mountForm(`
        <field name="module_muk_ai_skills"
               widget="module_link"
               options="{'url': 'https://my.mukit.at/r/skills'}"/>`);
    expect('a.o_module_link').toHaveAttribute('href', 'https://my.mukit.at/r/skills');
});

test('ticking the checkbox writes the field back to the record', async () => {
    onRpc('web_save', ({ args }) => {
        expect.step(`web_save:${args[1].module_muk_ai_schedule}`);
    });
    await mountForm('<field name="module_muk_ai_schedule" widget="module_link"/>');
    await contains('[name="module_muk_ai_schedule"] input[type="checkbox"]').click();
    await animationFrame();
    expect(queryOne('[name="module_muk_ai_schedule"] input').checked).toBe(true);
    await contains('.o_form_button_save').click();
    expect.verifySteps(['web_save:true']);
});
