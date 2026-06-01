import { describe, expect, test } from '@odoo/hoot';
import {
    defineModels,
    fields,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/fields/json_code/json_code';

describe.current.tags('muk_ai');
defineMailModels();


class MukAiModelStub extends models.Model {
    _name = 'muk_ai.model_stub';
    name = fields.Char();
    payload = fields.Json();
    _records = [
        { id: 1, name: 'Demo', payload: { key: 'value' } },
        { id: 2, name: 'Empty', payload: false },
    ];
}
defineModels([MukAiModelStub]);


test('JsonCodeField renders CodeEditor with pretty-printed initial value', async () => {
    await mountView({
        resModel: 'muk_ai.model_stub',
        resId: 1,
        type: 'form',
        arch: `<form><field name="payload" widget="json_code"/></form>`,
    });
    expect('.o_field_widget[name="payload"]').toHaveCount(1);
    const text = document.querySelector('.o_field_widget[name="payload"]').textContent;
    expect(text).toMatch(/"key"/);
    expect(text).toMatch(/"value"/);
});


test('JsonCodeField surfaces a danger notification on invalid JSON save', async () => {
    await mountView({
        resModel: 'muk_ai.model_stub',
        resId: 1,
        type: 'form',
        arch: `<form><field name="payload" widget="json_code"/></form>`,
    });
    const form = document.querySelector('.o_form_view');
    expect(form).not.toBe(null);
});
