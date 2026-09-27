import { describe, expect, test } from '@odoo/hoot';
import { session } from '@web/session';
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import '@muk_web_utils/views/fields/many2one/many2one';

describe.current.tags('muk_web_utils', 'desktop');

class Category extends models.Model {
    _name = 'muk_web_utils.category';
    name = fields.Char();
    _records = [{ id: 1, name: 'Existing' }];
}

class Item extends models.Model {
    _name = 'muk_web_utils.item';
    name = fields.Char();
    category_id = fields.Many2one({ relation: 'muk_web_utils.category' });
    _records = [{ id: 1, name: 'Item', category_id: false }];
}

defineModels([Category, Item]);

/**
 * Mount the item form and type a value into the many2one input.
 * @param {string} arch the form arch to mount
 * @returns {Promise<void>}
 */
async function typeInMany2one(arch) {
    await mountView({
        type: 'form',
        resModel: 'muk_web_utils.item',
        resId: 1,
        arch,
    });
    await contains('[name="category_id"] input').edit('Brand New', {
        confirm: false,
    });
    await contains('[name="category_id"] input').click();
}

test('quick create is offered when the session flag is off', async () => {
    patchWithCleanup(session, { disable_quick_create: false });
    await typeInMany2one('<form><field name="category_id"/></form>');
    expect('.o_m2o_dropdown_option_create').toHaveCount(1);
    expect('.o_m2o_dropdown_option_create_edit').toHaveCount(1);
});

test('quick create is suppressed when the session flag is on', async () => {
    patchWithCleanup(session, { disable_quick_create: true });
    await typeInMany2one('<form><field name="category_id"/></form>');
    expect('.o_m2o_dropdown_option_create').toHaveCount(0);
    expect('.o_m2o_dropdown_option_create_edit').toHaveCount(1);
});

test('an explicit no_quick_create option overrides the session flag', async () => {
    patchWithCleanup(session, { disable_quick_create: true });
    await typeInMany2one(
        `<form>
            <field name="category_id" options="{'no_quick_create': False}"/>
        </form>`,
    );
    expect('.o_m2o_dropdown_option_create').toHaveCount(1);
});

test('widgets built from the core many2one helper honour the flag too', async () => {
    patchWithCleanup(session, { disable_quick_create: true });
    await typeInMany2one(
        '<form><field name="category_id" widget="many2one_avatar"/></form>',
    );
    expect('.o_m2o_dropdown_option_create').toHaveCount(0);
    expect('.o_m2o_dropdown_option_create_edit').toHaveCount(1);
});
