import { describe, expect, test } from '@odoo/hoot';
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

/**
 * Read the choices the effort field offers.
 *
 * This Odoo renders a selection field as a native ``select``, so the choices
 * are in the DOM already and the first option is the empty placeholder.
 * @returns {Array} the option labels, without the placeholder
 */
function choiceLabels() {
    const options = document.querySelectorAll('.o_field_widget[name="effort"] option');
    return [...options].map((option) => option.textContent.trim()).filter(Boolean);
}

test('FilteredSelectionField limits choices to the supported options', async () => {
    await mountView({
        resModel: 'muk_ai.effort_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    expect(choiceLabels()).toEqual(['Low', 'High']);
});

test('FilteredSelectionField falls back to every choice without options', async () => {
    await mountView({
        resModel: 'muk_ai.effort_model',
        resId: 2,
        type: 'form',
        arch: ARCH,
    });
    expect(choiceLabels().length).toBe(6);
});
