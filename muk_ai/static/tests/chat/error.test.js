import { describe, expect, test } from '@odoo/hoot';

import { formatError } from '@muk_ai/chat/utils';

describe.current.tags('muk_ai');

test('formatError prefers data.message (Odoo RPC error shape)', () => {
    expect(
        formatError({
            data: { message: 'detail' },
            message: 'generic',
        }),
    ).toBe('detail');
});

test('formatError falls back to message when data.message is missing', () => {
    expect(formatError({ message: 'boom' })).toBe('boom');
    expect(formatError({ data: {}, message: 'boom' })).toBe('boom');
});

test('formatError stringifies primitives and unknown shapes', () => {
    expect(formatError('plain')).toBe('plain');
    expect(formatError(42)).toBe('42');
    expect(formatError(null)).toBe('null');
    expect(formatError(undefined)).toBe('undefined');
});

test('formatError works on real Error objects', () => {
    expect(formatError(new Error('wat'))).toBe('wat');
});

test('formatError handles empty-string message by falling back to String()', () => {
    expect(formatError({ message: '' })).toBe('[object Object]');
});
