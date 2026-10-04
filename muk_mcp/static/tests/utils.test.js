import { describe, expect, test } from '@odoo/hoot';

import { buildInitialValue, cleanValue } from '@muk_mcp/playground/utils/utils';

describe.current.tags('muk_mcp');

test('the initial value seeds required and defaulted properties only', () => {
    const value = buildInitialValue({
        type: 'object',
        required: ['text', 'list', 'flag', 'count', 'choice', 'object', 'untyped'],
        properties: {
            text: { type: 'string' },
            list: { type: 'array' },
            flag: { type: ['boolean', 'null'] },
            count: { type: 'integer' },
            choice: { enum: ['asc', 'desc'] },
            object: { type: 'object' },
            untyped: {},
            defaulted: { type: 'array', default: [1] },
            optional: { type: 'string' },
        },
    });
    expect(value).toEqual({
        text: '',
        list: [],
        flag: false,
        count: null,
        choice: 'asc',
        object: {},
        defaulted: [1],
    });
});

test('cleaning drops empty object members at every level and keeps 0 and false', () => {
    expect(
        cleanValue({
            empty: '',
            none: null,
            missing: undefined,
            zero: 0,
            no: false,
            nested: { keep: 1, drop: '' },
            list: [0, '', null, { drop: null }],
        }),
    ).toEqual({ zero: 0, no: false, nested: { keep: 1 }, list: [0, '', null, {}] });
});
