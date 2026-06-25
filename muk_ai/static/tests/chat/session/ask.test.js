import { describe, expect, test } from '@odoo/hoot';

import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';

describe.current.tags('muk_ai');

test('askArgsText pretty-prints preview.arguments JSON', () => {
    const text = askArgsText({
        preview: { arguments: { ids: [1, 2], model: 'res.partner' } },
    });
    expect(text).toBe(
        '{\n  "ids": [\n    1,\n    2\n  ],\n  "model": "res.partner"\n}',
    );
});

test('askArgsText falls back to preview itself when no .arguments key', () => {
    const text = askArgsText({ preview: { kind: 'delete', ids: [9] } });
    expect(JSON.parse(text)).toEqual({ kind: 'delete', ids: [9] });
});

test('askArgsText returns empty-object JSON for missing preview', () => {
    expect(askArgsText({})).toBe('{}');
    expect(askArgsText(null)).toBe('{}');
    expect(askArgsText(undefined)).toBe('{}');
});

test('askArgsText degrades to String() on circular structures', () => {
    const obj = { a: 1 };
    obj.self = obj;
    const text = askArgsText({ preview: { arguments: obj } });
    expect(text).toBe(String(obj));
});

test('askViewMode defaults to human when preview.kind exists', () => {
    expect(askViewMode({ callId: 'c1', preview: { kind: 'delete' } }, {})).toBe(
        'human',
    );
});

test('askViewMode defaults to technical when no preview.kind', () => {
    expect(askViewMode({ callId: 'c1', preview: {} }, {})).toBe('technical');
    expect(askViewMode({ callId: 'c1' }, {})).toBe('technical');
});

test('askViewMode honors explicit override per callId', () => {
    expect(
        askViewMode({ callId: 'c1', preview: { kind: 'delete' } }, { c1: 'technical' }),
    ).toBe('technical');
});

test('askViewMode handles missing block / overrides', () => {
    expect(askViewMode(null, { c1: 'human' })).toBe('technical');
    expect(askViewMode({ callId: 'c1', preview: { kind: 'delete' } }, null)).toBe(
        'human',
    );
});

test('toggleAskViewMode flips current mode', () => {
    const block = { callId: 'c1', preview: { kind: 'delete' } };
    expect(toggleAskViewMode(block, {})).toBe('technical');
    expect(toggleAskViewMode(block, { c1: 'technical' })).toBe('human');
    const blockNoKind = { callId: 'c2' };
    expect(toggleAskViewMode(blockNoKind, {})).toBe('human');
});
