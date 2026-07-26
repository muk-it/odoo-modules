import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import {
    clickSave,
    defineModels,
    editAce,
    fields,
    models,
    mockService,
    mountView,
    onRpc,
    patchWithCleanup,
    preloadBundle,
    preventResizeObserverError,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { JsonCodeField } from '@muk_ai/views/fields/json_code/json_code';

describe.current.tags('muk_ai');
defineMailModels();
preloadBundle('web.ace_lib');
preventResizeObserverError();

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

const ARCH = `<form><field name="payload" widget="json_code"/></form>`;

/**
 * Mount the stub form and record every value sent to ``web_save``.
 * @param {number} [resId] record to open
 * @returns {Promise<Array>} the list of written value dicts, filled as saves happen
 */
async function mountFormRecordingSaves(resId = 1) {
    const saved = [];
    onRpc('muk_ai.model_stub', 'web_save', ({ args }) => {
        saved.push(args[1]);
    });
    await mountView({ resModel: 'muk_ai.model_stub', resId, type: 'form', arch: ARCH });
    return saved;
}

test('JsonCodeField renders CodeEditor with pretty-printed initial value', async () => {
    await mountView({
        resModel: 'muk_ai.model_stub',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    expect('.o_field_widget[name="payload"] .ace_content').toHaveCount(1);
    const text = document.querySelector('.o_field_widget[name="payload"]').textContent;
    expect(text).toMatch(/"key"/);
    expect(text).toMatch(/"value"/);
});

test('JsonCodeField writes the parsed object rather than the edited text', async () => {
    const saved = await mountFormRecordingSaves();
    await editAce('{"a": [1, 2], "b": {"c": true}}');
    await clickSave();
    expect(saved).toEqual([{ payload: { a: [1, 2], b: { c: true } } }]);
});

test('JsonCodeField stores false when the editor is cleared', async () => {
    const saved = await mountFormRecordingSaves();
    await editAce('   ');
    await clickSave();
    expect(saved).toEqual([{ payload: false }]);
});

test('JsonCodeField surfaces a danger notification on invalid JSON', async () => {
    const notified = [];
    mockService('notification', {
        add(message, options) {
            notified.push({ message, options });
            return () => {};
        },
    });
    const saved = await mountFormRecordingSaves();
    await editAce('{"a": ');
    await animationFrame();
    expect(saved).toEqual([]);
    expect(notified).toHaveLength(1);
    expect(notified[0].message).toInclude('Invalid JSON in payload');
    expect(notified[0].message).toInclude('Unexpected end of JSON input');
    expect(notified[0].options.type).toBe('danger');
    expect(notified[0].options.sticky).toBe(true);
});

test('JsonCodeField marks the field invalid so the record cannot be saved', async () => {
    await mountFormRecordingSaves();
    await editAce('{"a": ');
    await animationFrame();
    expect('.o_field_widget[name="payload"]').toHaveClass('o_field_invalid');
    expect('.o_form_button_save:disabled').toHaveCount(1);
    expect('.o_form_button_save:enabled').toHaveCount(0);
});

test('JsonCodeField clears the invalid flag once the JSON parses again', async () => {
    const saved = await mountFormRecordingSaves();
    await editAce('{"a": ');
    await animationFrame();
    expect('.o_field_widget[name="payload"]').toHaveClass('o_field_invalid');
    await editAce('{"a": 1}');
    await animationFrame();
    expect('.o_field_widget[name="payload"]').not.toHaveClass('o_field_invalid');
    await clickSave();
    expect(saved).toEqual([{ payload: { a: 1 } }]);
});

test('an urgent save commits an edit the user never blurred out of', async () => {
    let field = null;
    const commits = [];
    patchWithCleanup(JsonCodeField.prototype, {
        setup() {
            super.setup();
            field = this;
        },
        commitChanges() {
            const prom = super.commitChanges();
            commits.push(prom);
            return prom;
        },
    });
    await mountView({
        resModel: 'muk_ai.model_stub',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    const record = field.props.record;
    field.handleChange('{"urgent": true}');
    expect(record.data.payload).toEqual({ key: 'value' });

    record.model.bus.trigger('WILL_SAVE_URGENTLY');
    await Promise.all(commits);
    expect(record.data.payload).toEqual({ urgent: true });
});

test('a local-changes request commits the pending edit before the caller proceeds', async () => {
    let field = null;
    patchWithCleanup(JsonCodeField.prototype, {
        setup() {
            super.setup();
            field = this;
        },
    });
    await mountView({
        resModel: 'muk_ai.model_stub',
        resId: 1,
        type: 'form',
        arch: ARCH,
    });
    const record = field.props.record;
    field.handleChange('{"local": 1}');
    expect(record.data.payload).toEqual({ key: 'value' });

    const proms = [];
    record.model.bus.trigger('NEED_LOCAL_CHANGES', { proms });
    expect(proms).toHaveLength(1);
    await Promise.all(proms);
    expect(record.data.payload).toEqual({ local: 1 });
});
