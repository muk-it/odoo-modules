import { describe, expect, test } from '@odoo/hoot';
import {
    clickSave,
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

describe.current.tags('muk_ai');
defineMailModels();

class MukAiPromptLead extends models.Model {
    _name = 'muk_ai.prompt_lead';
    stage = fields.Char({ string: 'Stage' });
}

class MukAiPromptStub extends models.Model {
    _name = 'muk_ai.prompt_stub';
    prompt = fields.Text();
    notes = fields.Text();
    prompt_model = fields.Char();
    _records = [{ id: 1, prompt_model: 'muk_ai.prompt_lead' }];
}
defineModels([MukAiPromptLead, MukAiPromptStub]);

test('a prompt inserts a field of its variable from the button, never on #', async () => {
    onRpc('has_group', () => true);
    onRpc('mail_allowed_qweb_expressions', () => []);
    const saved = [];
    onRpc('muk_ai.prompt_stub', 'web_save', ({ args }) => {
        saved.push(args[1]);
    });
    await mountView({
        resModel: 'muk_ai.prompt_stub',
        resId: 1,
        type: 'form',
        arch: `<form>
            <field name="prompt_model" invisible="1"/>
            <field name="prompt" widget="prompt" options="{'variable': 'record', 'res_model_field': 'prompt_model'}"/>
            <field name="notes" widget="prompt" options="{'res_model': 'muk_ai.prompt_lead'}"/>
        </form>`,
    });
    await contains('.o_field_widget[name=prompt] textarea').edit('# Hi ', {
        confirm: false,
    });
    expect('.o_model_field_selector_popover').toHaveCount(0);
    await contains('.o_field_widget[name=prompt] button.fa-magic').click();
    await contains('.o_model_field_selector_popover_item_name:contains(Stage)').click();
    await contains('.o_model_field_selector_default_value_input input').edit('new', {
        confirm: false,
    });
    await contains('.o_model_field_selector_popover button:contains(Insert)').click();
    await contains('.o_field_widget[name=notes] textarea').click();
    await contains('.o_field_widget[name=notes] button.fa-magic').click();
    await contains('.o_model_field_selector_popover_item_name:contains(Stage)').click();
    await contains('.o_model_field_selector_popover button:contains(Insert)').click();
    await clickSave();
    expect(saved).toEqual([
        { prompt: '# Hi {{record.stage ||| new}}', notes: '{{stage}}' },
    ]);
});
