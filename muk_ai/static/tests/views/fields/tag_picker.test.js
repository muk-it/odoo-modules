import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/fields/tag_picker/tag_picker';

describe.current.tags('muk_ai');
defineMailModels();


class MukAiTagModel extends models.Model {
    _name = 'muk_ai.tag_model';
    tools_available = fields.Json();
    tool_filter = fields.Json();
    _records = [{
        id: 1,
        tools_available: [
            { name: 'search_read', category: 'read' },
            { name: 'write_record', category: 'write' },
            { name: 'ask_user', category: 'read' },
        ],
        tool_filter: ['search_read'],
    }, {
        id: 2,
        tools_available: [
            { name: 'a', category: 'read' },
            { name: 'b', category: 'write' },
        ],
        tool_filter: false,
    }];
}
defineModels([MukAiTagModel]);


test('TagPickerField renders tag chips for each selected name', async () => {
    await mountView({
        resModel: 'muk_ai.tag_model',
        resId: 1,
        type: 'form',
        arch: `
            <form>
                <field name="tools_available" invisible="1"/>
                <field name="tool_filter" widget="tag_picker"
                       options="{'options_field': 'tools_available'}"/>
            </form>`,
    });
    expect('.o_tag').toHaveCount(1);
    expect(queryFirst('.o_tag').textContent).toMatch(/search_read/);
});


test('TagPickerField renders empty tag list when selection is false', async () => {
    await mountView({
        resModel: 'muk_ai.tag_model',
        resId: 2,
        type: 'form',
        arch: `
            <form>
                <field name="tools_available" invisible="1"/>
                <field name="tool_filter" widget="tag_picker"
                       options="{'options_field': 'tools_available'}"/>
            </form>`,
    });
    expect('.o_tag').toHaveCount(0);
});


test('TagPickerField autocomplete input is present and opens a dropdown', async () => {
    await mountView({
        resModel: 'muk_ai.tag_model',
        resId: 1,
        type: 'form',
        arch: `
            <form>
                <field name="tools_available" invisible="1"/>
                <field name="tool_filter" widget="tag_picker"
                       options="{'options_field': 'tools_available'}"/>
            </form>`,
    });
    const input = queryFirst('.o-autocomplete--input');
    expect(input).not.toBe(null);
    await click(input);
});
