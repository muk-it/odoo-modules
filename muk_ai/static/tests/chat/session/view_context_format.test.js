import { describe, expect, test } from '@odoo/hoot';
import { patchTranslations } from '@web/../tests/web_test_helpers';

import {
    viewContextLabel,
    viewContextTooltip,
} from '@muk_ai/chat/session/view_context_format';

describe.current.tags('muk_ai');
patchTranslations();

test('viewContextLabel returns empty string for falsy ctx', () => {
    expect(viewContextLabel(null)).toBe('');
    expect(viewContextLabel(undefined)).toBe('');
});

test('viewContextLabel renders a record with display_name', () => {
    expect(
        viewContextLabel({
            kind: 'record',
            model: 'res.partner',
            display_name: 'Acme',
            id: 12,
        }),
    ).toBe('res.partner · Acme');
});

test('viewContextLabel falls back to #id when display_name missing', () => {
    expect(
        viewContextLabel({
            kind: 'record',
            model: 'res.partner',
            id: 5,
        }),
    ).toBe('res.partner · #5');
});

test('viewContextLabel returns model only when neither display_name nor id', () => {
    expect(viewContextLabel({ kind: 'record', model: 'res.partner' })).toBe(
        'res.partner',
    );
});

test('viewContextLabel renders a list with view_type', () => {
    expect(
        viewContextLabel({
            kind: 'list',
            model: 'sale.order',
            view_type: 'kanban',
        }),
    ).toBe('sale.order · kanban');
});

test('viewContextLabel defaults list view_type to "list"', () => {
    expect(viewContextLabel({ kind: 'list', model: 'sale.order' })).toBe(
        'sale.order · list',
    );
});

test('viewContextLabel for action falls back to "Action" when model is empty', () => {
    expect(String(viewContextLabel({ kind: 'action' }))).toBe('Action');
    expect(viewContextLabel({ kind: 'action', model: 'crm.lead' })).toBe('crm.lead');
});

test('viewContextLabel uses model when kind is unknown', () => {
    expect(viewContextLabel({ kind: 'mystery', model: 'res.users' })).toBe('res.users');
    expect(viewContextLabel({ kind: 'mystery' })).toBe('');
});

test('viewContextTooltip combines label and hint', () => {
    const tip = String(
        viewContextTooltip({
            kind: 'record',
            model: 'res.partner',
            display_name: 'Acme',
        }),
    );
    expect(tip).toMatch(/^res\.partner · Acme\n/);
    expect(tip).toMatch(/Click to open · \/unpin to clear$/);
});

test('viewContextTooltip injects domain JSON only for non-empty list domains', () => {
    const withDomain = String(
        viewContextTooltip({
            kind: 'list',
            model: 'sale.order',
            domain: [['state', '=', 'sale']],
        }),
    );
    expect(withDomain.split('\n')).toEqual([
        'sale.order · list',
        '[["state","=","sale"]]',
        'Click to open · /unpin to clear',
    ]);
    const empty = String(
        viewContextTooltip({
            kind: 'list',
            model: 'sale.order',
            domain: [],
        }),
    );
    expect(empty.split('\n').length).toBe(2);
    const recordTip = String(
        viewContextTooltip({
            kind: 'record',
            model: 'res.partner',
            domain: [['x', '=', 1]],
        }),
    );
    expect(recordTip.split('\n').length).toBe(2);
});

test('viewContextTooltip is empty for falsy ctx', () => {
    expect(viewContextTooltip(null)).toBe('');
});
