import { describe, expect, test } from '@odoo/hoot';
import { queryAllTexts, queryOne } from '@odoo/hoot-dom';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { contains, mountWithCleanup } from '@web/../tests/web_test_helpers';

import { SchemaForm } from '@muk_mcp/playground/schema_form/schema_form';

describe.current.tags('muk_mcp');

defineMailModels();

async function mountForm(properties, value = {}) {
    const changes = [];
    await mountWithCleanup(SchemaForm, {
        props: {
            schema: { type: 'object', required: ['model'], properties },
            value,
            onChange: (next) => changes.push(next),
        },
    });
    return changes;
}

test('an empty schema renders the no-parameter hint', async () => {
    await mountForm({});
    expect('.text-muted').toHaveText('This tool takes no parameters.');
});

test('each property renders the input matching its type', async () => {
    await mountForm({
        model: { type: 'string', description: 'Technical model name' },
        limit: { type: 'integer' },
        ratio: { type: 'number' },
        active_test: { type: 'boolean' },
        order: { type: 'string', enum: ['asc', 'desc'] },
        domain: { type: 'array' },
    });
    expect(queryAllTexts('.form-label .fw-bold')).toEqual([
        'model',
        'limit',
        'ratio',
        'active_test',
        'order',
        'domain',
    ]);
    for (const selector of [
        'input[type=text]',
        'input[type=number][step="1"]',
        'input[type=number][step=any]',
        'input[type=checkbox]',
        'select',
        'textarea',
    ]) {
        expect(selector).toHaveCount(1);
    }
    expect('.form-label .text-danger').toHaveCount(1);
    expect('.form-text:first').toHaveText('Technical model name');
});

test('editing a field emits the merged value and clearing it removes the key', async () => {
    const changes = await mountForm(
        {
            model: { type: 'string' },
            limit: { type: 'integer' },
            ratio: { type: 'number' },
            order: { type: 'string', enum: ['asc', 'desc'] },
        },
        { keep: 1 },
    );
    for (const [selector, input, expected] of [
        ['input[type=text]', 'res.partner', { keep: 1, model: 'res.partner' }],
        ['input[step="1"]', '42', { keep: 1, limit: 42 }],
        ['input[step=any]', '1.5', { keep: 1, ratio: 1.5 }],
        ['input[step="1"]', '', { keep: 1 }],
    ]) {
        await contains(selector).edit(input, { instantly: true });
        expect(changes.at(-1)).toEqual(expected);
    }
    await contains('select').select('desc');
    expect(changes.at(-1)).toEqual({ keep: 1, order: 'desc' });
    await contains('select').select('');
    expect(changes.at(-1)).toEqual({ keep: 1 });
});

test('the boolean switch emits true and false', async () => {
    const changes = await mountForm({ active_test: { type: 'boolean' } });
    await contains('input[type=checkbox]').check();
    expect(changes.at(-1)).toEqual({ active_test: true });
    await contains('input[type=checkbox]').uncheck();
    expect(changes.at(-1)).toEqual({ active_test: false });
});

test('the JSON field parses valid input and flags invalid input', async () => {
    const changes = await mountForm({ domain: { type: 'array' } }, { domain: [] });
    expect('textarea').toHaveValue('[]');
    await contains('textarea').edit('[["id", "=", 1]]');
    expect(changes.at(-1)).toEqual({ domain: [['id', '=', 1]] });
    expect(queryOne('textarea').validationMessage).toBe('');
    const count = changes.length;
    await contains('textarea').edit('[[unclosed', { instantly: true });
    expect(changes.slice(count)).toEqual([{}]);
    expect(queryOne('textarea').validationMessage).not.toBe('');
});
