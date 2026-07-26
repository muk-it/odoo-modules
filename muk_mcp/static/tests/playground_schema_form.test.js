import { describe, expect, test } from '@odoo/hoot';
import {
    check,
    click,
    edit,
    queryAllTexts,
    queryOne,
    select,
    uncheck,
} from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';

import { SchemaForm } from '@muk_mcp/playground/schema_form';

describe.current.tags('muk_mcp');

defineMailModels();

function makeForm(schema, value = {}) {
    const inst = Object.create(SchemaForm.prototype);
    inst.props = { schema, value, onChange: () => {} };
    return inst;
}

async function mountForm(schema, value = {}) {
    const changes = [];
    await mountWithCleanup(SchemaForm, {
        props: {
            schema,
            value,
            onChange: (next) => changes.push(next),
        },
    });
    return changes;
}

test('fields returns empty array for non-object schema', () => {
    expect(makeForm({ type: 'string' }).fields).toEqual([]);
});

test('fields lists each property with its kind and required flag', () => {
    const inst = makeForm({
        type: 'object',
        required: ['model'],
        properties: {
            model: { type: 'string' },
            domain: { type: 'array' },
            active_test: { type: 'boolean' },
        },
    });
    const fields = inst.fields;
    expect(fields.length).toBe(3);
    const byName = Object.fromEntries(fields.map((f) => [f.name, f]));
    expect(byName.model.kind).toBe('string');
    expect(byName.model.required).toBe(true);
    expect(byName.domain.kind).toBe('json');
    expect(byName.domain.required).toBe(false);
    expect(byName.active_test.kind).toBe('bool');
});

test('getValue reads nested property from props.value', () => {
    const inst = makeForm({ type: 'object', properties: {} }, { name: 'Alice' });
    expect(inst.getValue('name')).toBe('Alice');
    expect(inst.getValue('missing')).toBe(undefined);
});

test('setValue emits the merged dict via onChange', () => {
    let captured = null;
    const inst = Object.create(SchemaForm.prototype);
    inst.props = {
        schema: { type: 'object', properties: {} },
        value: { a: 1 },
        onChange: (next) => {
            captured = next;
        },
    };
    inst.setValue('b', 2);
    expect(captured).toEqual({ a: 1, b: 2 });
});

test('setValue removes keys when the new value is undefined or empty string', () => {
    let captured = null;
    const inst = Object.create(SchemaForm.prototype);
    inst.props = {
        schema: { type: 'object', properties: {} },
        value: { a: 1, b: 2 },
        onChange: (next) => {
            captured = next;
        },
    };
    inst.setValue('a', '');
    expect(captured).toEqual({ b: 2 });
    inst.setValue('b', undefined);
    expect(captured).toEqual({ a: 1 });
});

test('jsonText stringifies complex values', () => {
    const inst = makeForm({ type: 'object', properties: {} }, { arr: [1, 2] });
    expect(inst.jsonText('arr')).toBe('[\n  1,\n  2\n]');
});

test('jsonText returns empty string for undefined or null', () => {
    const inst = makeForm({ type: 'object', properties: {} }, {});
    expect(inst.jsonText('missing')).toBe('');
});

// ----------------------------------------------------------
// Rendered widgets
// ----------------------------------------------------------

test('an empty schema renders the no-parameter hint', async () => {
    await mountForm({ type: 'object', properties: {} });
    expect('.text-muted').toHaveText('This tool takes no parameters.');
});

test('each property renders the widget matching its kind', async () => {
    await mountForm({
        type: 'object',
        required: ['model'],
        properties: {
            model: { type: 'string', description: 'Technical model name' },
            limit: { type: 'integer' },
            ratio: { type: 'number' },
            active_test: { type: 'boolean' },
            order: { type: 'string', enum: ['asc', 'desc'] },
            domain: { type: 'array' },
        },
    });
    expect('input[type="text"]').toHaveCount(1);
    expect('input[type="number"][step="1"]').toHaveCount(1);
    expect('input[type="number"][step="any"]').toHaveCount(1);
    expect('input[type="checkbox"]').toHaveCount(1);
    expect('select').toHaveCount(1);
    expect('textarea').toHaveCount(1);
    expect(queryAllTexts('.form-label .fw-bold')).toEqual([
        'model',
        'limit',
        'ratio',
        'active_test',
        'order',
        'domain',
    ]);
    expect('.form-label .text-danger').toHaveCount(1);
    expect(queryAllTexts('.form-text')[0]).toBe('Technical model name');
});

test('editing a string field emits the merged value and clearing removes it', async () => {
    const changes = await mountForm(
        { type: 'object', properties: { model: { type: 'string' } } },
        { limit: 5 },
    );
    await click('input[type="text"]');
    await edit('res.partner', { instantly: true });
    await animationFrame();
    expect(changes).toEqual([{ limit: 5, model: 'res.partner' }]);
    await click('input[type="text"]');
    await edit('');
    await animationFrame();
    expect(changes.at(-1)).toEqual({ limit: 5 });
});

test('integer and number fields parse their input', async () => {
    const changes = await mountForm({
        type: 'object',
        properties: { limit: { type: 'integer' }, ratio: { type: 'number' } },
    });
    await click('input[step="1"]');
    await edit('42', { instantly: true });
    await animationFrame();
    expect(changes).toEqual([{ limit: 42 }]);
    await click('input[step="any"]');
    await edit('1.5', { instantly: true });
    await animationFrame();
    expect(changes.at(-1)).toEqual({ ratio: 1.5 });
    await click('input[step="1"]');
    await edit('');
    await animationFrame();
    expect(changes.at(-1)).toEqual({});
});

test('the boolean switch emits true and false', async () => {
    const changes = await mountForm({
        type: 'object',
        properties: { active_test: { type: 'boolean' } },
    });
    await check('input[type="checkbox"]');
    await animationFrame();
    expect(changes.at(-1)).toEqual({ active_test: true });
    await uncheck('input[type="checkbox"]');
    await animationFrame();
    expect(changes.at(-1)).toEqual({ active_test: false });
});

test('the enum select emits the option and drops the empty choice', async () => {
    const changes = await mountForm({
        type: 'object',
        properties: { order: { type: 'string', enum: ['asc', 'desc'] } },
    });
    await select('desc', { target: 'select' });
    await animationFrame();
    expect(changes.at(-1)).toEqual({ order: 'desc' });
    await select('', { target: 'select' });
    await animationFrame();
    expect(changes.at(-1)).toEqual({});
});

test('the raw JSON field parses valid input and flags invalid input', async () => {
    const changes = await mountForm({
        type: 'object',
        properties: { domain: { type: 'array' } },
    });
    await click('textarea');
    await edit('[["id", "=", 1]]', { instantly: true });
    await animationFrame();
    expect(changes).toEqual([{ domain: [['id', '=', 1]] }]);
    expect(queryOne('textarea').validationMessage).toBe('');
    await click('textarea');
    await edit('[[unclosed', { instantly: true });
    await animationFrame();
    expect(changes).toHaveLength(2);
    expect(changes.at(-1)).toEqual({});
    expect(queryOne('textarea').validationMessage).not.toBe('');
    await click('textarea');
    await edit('   ', { instantly: true });
    await animationFrame();
    expect(changes.at(-1)).toEqual({});
});
