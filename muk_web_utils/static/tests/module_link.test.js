import { describe, expect, test } from '@odoo/hoot';
import { queryFirst } from '@odoo/hoot-dom';
import {
    defineModels,
    fields,
    models,
    mountView,
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

const ARCH = `
    <form>
        <field name="module_muk_ai_schedule" widget="module_link"/>
        <field name="module_muk_ai_skills" widget="module_link"/>
    </form>`;

test('ModuleLinkField renders a checkbox when the module is on disk', async () => {
    await mountView({
        resModel: 'muk_web_utils.module_link_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    const scheduleCell = queryFirst('[name="module_muk_ai_schedule"]');
    expect(scheduleCell.querySelector('input[type="checkbox"]')).not.toBe(null);
    expect(scheduleCell.querySelector('a.o_module_link')).toBe(null);
});

test('ModuleLinkField renders an Apps store link when the module is missing', async () => {
    await mountView({
        resModel: 'muk_web_utils.module_link_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    const skillsCell = queryFirst('[name="module_muk_ai_skills"]');
    expect(skillsCell.querySelector('input[type="checkbox"]')).toBe(null);
    const link = skillsCell.querySelector('a.o_module_link');
    expect(link).not.toBe(null);
    expect(link.getAttribute('href')).toBe(
        'https://apps.odoo.com/apps/modules/19.0/muk_ai_skills',
    );
    expect(link.getAttribute('target')).toBe('_blank');
});

test('ModuleLinkField uses the url option when provided', async () => {
    await mountView({
        resModel: 'muk_web_utils.module_link_model',
        resId: 1,
        type: 'form',
        arch: `
            <form>
                <field name="module_muk_ai_skills"
                       widget="module_link"
                       options="{'url': 'https://my.mukit.at/r/skills'}"/>
            </form>`,
    });
    const link = queryFirst('a.o_module_link');
    expect(link.getAttribute('href')).toBe('https://my.mukit.at/r/skills');
});
