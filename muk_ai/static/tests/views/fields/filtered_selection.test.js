import { describe, expect, test } from '@odoo/hoot';
import { animationFrame, click } from '@odoo/hoot-dom';
import {
    defineModels,
    fields,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/fields/filtered_selection/filtered_selection';

describe.current.tags('muk_ai');
defineMailModels();

const ARCH = `
    <form>
        <field name="effort_options" invisible="1"/>
        <field name="effort" widget="filtered_selection"
               options="{'options_field': 'effort_options'}"/>
    </form>`;

class MukAiEffortModel extends models.Model {
    _name = 'muk_ai.effort_model';
    effort = fields.Selection({
        selection: [
            ['minimal', 'Minimal'],
            ['low', 'Low'],
            ['medium', 'Medium'],
            ['high', 'High'],
            ['xhigh', 'Extra High'],
            ['max', 'Maximum'],
        ],
    });
    effort_options = fields.Json();
    _records = [
        { id: 1, effort: 'low', effort_options: ['low', 'high'] },
        { id: 2, effort: false, effort_options: false },
    ];
}
defineModels([MukAiEffortModel]);

test('FilteredSelectionField limits choices to the supported options', async () => {
    await mountView({
        resModel: 'muk_ai.effort_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    await click('.o_field_widget[name="effort"] .o_select_menu_toggler');
    await animationFrame();
    const labels = [...document.querySelectorAll('.o_select_menu_item')].map((el) =>
        el.textContent.trim(),
    );
    expect(labels).toEqual(['Low', 'High']);
});

test('FilteredSelectionField falls back to every choice without options', async () => {
    await mountView({
        resModel: 'muk_ai.effort_model',
        resId: 2,
        type: 'form',
        arch: ARCH,
    });
    await click('.o_field_widget[name="effort"] .o_select_menu_toggler');
    await animationFrame();
    expect(document.querySelectorAll('.o_select_menu_item').length).toBe(6);
});
