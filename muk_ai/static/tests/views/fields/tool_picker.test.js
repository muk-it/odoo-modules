import { describe, expect, test } from '@odoo/hoot';
import { queryAllTexts, queryFirst } from '@odoo/hoot-dom';
import { runAllTimers } from '@odoo/hoot-mock';
import {
    clickSave,
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/fields/tool_picker/tool_picker';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();

class MukAiToolModel extends models.Model {
    _name = 'muk_ai.tool_model';
    tools_available = fields.Json();
    tool_filter = fields.Json();
    _records = [
        {
            id: 1,
            tools_available: [
                { name: 'search_read', category: 'read' },
                { name: 'write_record', category: 'write' },
                { name: 'ask_user', category: 'read' },
            ],
            tool_filter: ['search_read'],
        },
        {
            id: 2,
            tools_available: [
                { name: 'a', category: 'read' },
                { name: 'b', category: 'write' },
            ],
            tool_filter: false,
        },
    ];
}
defineModels([MukAiToolModel]);

const ARCH = `
    <form>
        <field name="tools_available" invisible="1"/>
        <field name="tool_filter" widget="tool_picker"
               options="{'options_field': 'tools_available'}"/>
    </form>`;

/**
 * Mount the picker form and record every value sent to ``web_save``.
 * @param {number} resId record to open
 * @returns {Promise<Array>} the list of written value dicts, filled as saves happen
 */
async function mountFormRecordingSaves(resId) {
    const saved = [];
    onRpc('muk_ai.tool_model', 'web_save', ({ args }) => {
        saved.push(args[1]);
    });
    await mountView({ resModel: 'muk_ai.tool_model', resId, type: 'form', arch: ARCH });
    return saved;
}

test('ToolPickerField renders tag chips for each selected name', async () => {
    await mountView({
        resModel: 'muk_ai.tool_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    expect('.o_tag').toHaveCount(1);
    expect(queryFirst('.o_tag').textContent).toMatch(/search_read/);
});

test('ToolPickerField renders empty tag list when selection is false', async () => {
    await mountView({
        resModel: 'muk_ai.tool_model',
        resId: 2,
        type: 'form',
        arch: ARCH,
    });
    expect('.o_tag').toHaveCount(0);
});

test('the dropdown offers every catalog tool that is not already picked', async () => {
    await mountView({
        resModel: 'muk_ai.tool_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    await contains('.o-autocomplete--input').click();
    await runAllTimers();
    expect(queryAllTexts('.o-autocomplete--dropdown-item')).toEqual([
        'write_record',
        'ask_user',
    ]);
});

test('the dropdown narrows down to the tools matching the typed term', async () => {
    await mountView({
        resModel: 'muk_ai.tool_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    await contains('.o-autocomplete--input').edit('rec', { confirm: false });
    await runAllTimers();
    expect(queryAllTexts('.o-autocomplete--dropdown-item')).toEqual(['write_record']);
});

test('picking a tool appends it to the stored filter', async () => {
    const saved = await mountFormRecordingSaves(1);
    await contains('.o-autocomplete--input').click();
    await runAllTimers();
    await contains('.o-autocomplete--dropdown-item', { text: 'write_record' }).click();
    expect(queryAllTexts('.o_tag')).toEqual(['search_read', 'write_record']);
    await clickSave();
    expect(saved).toEqual([{ tool_filter: ['search_read', 'write_record'] }]);
});

test('picking a tool on an empty filter starts a fresh list', async () => {
    const saved = await mountFormRecordingSaves(2);
    await contains('.o-autocomplete--input').click();
    await runAllTimers();
    await contains('.o-autocomplete--dropdown-item', { text: 'b' }).click();
    await clickSave();
    expect(saved).toEqual([{ tool_filter: ['b'] }]);
});

test('removing the last tool clears the filter to false rather than an empty list', async () => {
    const saved = await mountFormRecordingSaves(1);
    await contains('.o_tag .o_delete').click();
    expect('.o_tag').toHaveCount(0);
    await clickSave();
    expect(saved).toEqual([{ tool_filter: false }]);
});

test('a term matching nothing shows an unselectable hint instead of an option', async () => {
    await mountView({
        resModel: 'muk_ai.tool_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    await contains('.o-autocomplete--input').edit('zzz', { confirm: false });
    await runAllTimers();
    expect(queryAllTexts('.o-autocomplete--dropdown-item')).toEqual([
        'No matching tool',
    ]);
    expect('.o-autocomplete--dropdown-item.fst-italic').toHaveCount(1);
    expect('.o-autocomplete--dropdown-item a').toHaveCount(0);
    await contains('.o-autocomplete--dropdown-item').click();
    expect(queryAllTexts('.o_tag')).toEqual(['search_read']);
});

test('an already picked tool disappears from the dropdown', async () => {
    await mountView({
        resModel: 'muk_ai.tool_model',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    await contains('.o-autocomplete--input').click();
    await runAllTimers();
    await contains('.o-autocomplete--dropdown-item', { text: 'ask_user' }).click();
    await contains('.o-autocomplete--input').click();
    await runAllTimers();
    expect(queryAllTexts('.o-autocomplete--dropdown-item')).toEqual(['write_record']);
});
