import { describe, expect, test } from '@odoo/hoot';

import { buildRenderedTurns } from '@muk_ai/chat/session/turns';

describe.current.tags('muk_ai');

test('returns empty list for empty / nullish log', () => {
    expect(buildRenderedTurns([])).toEqual([]);
    expect(buildRenderedTurns(null)).toEqual([]);
    expect(buildRenderedTurns(undefined)).toEqual([]);
});

test('user_message becomes a user turn carrying attachments', () => {
    const turns = buildRenderedTurns([
        { kind: 'user_message', content: 'hi', attachments: [{ id: 1 }] },
    ]);
    expect(turns).toEqual([{ role: 'user', text: 'hi', attachments: [{ id: 1 }] }]);
});

test('answer kind becomes a user turn (uses entry.answer)', () => {
    const turns = buildRenderedTurns([
        { kind: 'answer', answer: 'yes', attachments: [] },
    ]);
    expect(turns).toEqual([{ role: 'user', text: 'yes', attachments: [] }]);
});

test('user turns carry the entry _clientKey as clientKey', () => {
    const turns = buildRenderedTurns([
        { kind: 'user_message', content: 'hi', attachments: [], _clientKey: 'ck1' },
        { kind: 'answer', answer: 'yes', attachments: [], _clientKey: 'ck2' },
        { kind: 'user_message', content: 'bare', attachments: [] },
    ]);
    expect(turns[0].clientKey).toBe('ck1');
    expect(turns[1].clientKey).toBe('ck2');
    expect(turns[2].clientKey).toBe(undefined);
});

test('text and tool_call merge into one assistant turn', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'thinking…' },
        { kind: 'tool_call', name: 't1', arguments: { a: 1 }, call_id: 'c1' },
        { kind: 'text', content: ' done' },
    ]);
    expect(turns.length).toBe(1);
    expect(turns[0].role).toBe('assistant');
    expect(turns[0].blocks).toEqual([
        { type: 'text', text: 'thinking…' },
        { type: 'tool', name: 't1', arguments: { a: 1 }, callId: 'c1', result: null },
        { type: 'text', text: ' done' },
    ]);
});

test('consecutive text entries merge into a single block separated by blank line', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'first' },
        { kind: 'text', content: 'second' },
        { kind: 'text', content: 'third' },
    ]);
    expect(turns.length).toBe(1);
    expect(turns[0].blocks).toEqual([
        { type: 'text', text: 'first\n\nsecond\n\nthird' },
    ]);
});

test('text after a tool block starts a new text block (no merge across tools)', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'pre' },
        { kind: 'tool_call', name: 't1', arguments: {}, call_id: 'c1' },
        { kind: 'tool_result', call_id: 'c1', result: 'r' },
        { kind: 'text', content: 'post-a' },
        { kind: 'text', content: 'post-b' },
    ]);
    expect(turns.length).toBe(1);
    expect(turns[0].blocks.length).toBe(3);
    expect(turns[0].blocks[0]).toEqual({ type: 'text', text: 'pre' });
    expect(turns[0].blocks[1].type).toBe('tool');
    expect(turns[0].blocks[2]).toEqual({ type: 'text', text: 'post-a\n\npost-b' });
});

test('tool_result attaches to the matching tool_call by call_id', () => {
    const turns = buildRenderedTurns([
        { kind: 'tool_call', name: 't1', arguments: { a: 1 }, call_id: 'c1' },
        { kind: 'tool_result', call_id: 'c1', result: { ok: true } },
    ]);
    expect(turns[0].blocks[0].result).toEqual({ ok: true });
});

test('orphan tool_result without matching call gets its own block when assistant turn exists', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'pre' },
        { kind: 'tool_result', call_id: 'unknown', name: 'ghost', result: 'r' },
    ]);
    expect(turns[0].blocks).toEqual([
        { type: 'text', text: 'pre' },
        {
            type: 'tool',
            name: 'ghost',
            arguments: null,
            callId: 'unknown',
            result: 'r',
        },
    ]);
});

test('orphan tool_result with no current assistant turn is dropped (does not throw)', () => {
    const turns = buildRenderedTurns([
        { kind: 'tool_result', call_id: 'unknown', result: 'r' },
    ]);
    expect(turns).toEqual([]);
});

test('user_message resets the assistant accumulator (next text starts a new turn)', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'a' },
        { kind: 'user_message', content: 'next', attachments: [] },
        { kind: 'text', content: 'b' },
    ]);
    expect(turns.length).toBe(3);
    expect(turns[0]).toEqual({
        role: 'assistant',
        blocks: [{ type: 'text', text: 'a' }],
    });
    expect(turns[1].role).toBe('user');
    expect(turns[2]).toEqual({
        role: 'assistant',
        blocks: [{ type: 'text', text: 'b' }],
        regenerateAt: 0,
    });
});

test('ask_user creates an ask block with defaults for resolution and preview', () => {
    const turns = buildRenderedTurns([
        { kind: 'ask_user', text: 'continue?', options: ['yes', 'no'], call_id: 'a1' },
    ]);
    expect(turns[0].blocks[0]).toEqual({
        type: 'ask',
        text: 'continue?',
        options: ['yes', 'no'],
        preview: null,
        callId: 'a1',
        resolution: 'text',
    });
});

test('ask_user keeps explicit preview and resolution', () => {
    const turns = buildRenderedTurns([
        {
            kind: 'ask_user',
            text: 't',
            options: [],
            preview: { kind: 'delete' },
            resolution: 'option',
            call_id: 'a',
        },
    ]);
    expect(turns[0].blocks[0].preview).toEqual({ kind: 'delete' });
    expect(turns[0].blocks[0].resolution).toBe('option');
});

test('command becomes a standalone command turn with defaults', () => {
    const turns = buildRenderedTurns([
        { kind: 'command', name: '/compact', message: 'done', summary: 'x' },
    ]);
    expect(turns).toEqual([
        {
            role: 'command',
            name: '/compact',
            message: 'done',
            summary: 'x',
            originalMessages: 0,
            originalTokens: 0,
        },
    ]);
});

test('command resets the assistant accumulator', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'a' },
        { kind: 'command', name: '/compact' },
        { kind: 'text', content: 'b' },
    ]);
    expect(turns.length).toBe(3);
    expect(turns[0].role).toBe('assistant');
    expect(turns[1].role).toBe('command');
    expect(turns[2].role).toBe('assistant');
});

test('unknown kinds are ignored without breaking the rest', () => {
    const turns = buildRenderedTurns([
        { kind: 'mystery', content: 'x' },
        { kind: 'text', content: 'a' },
    ]);
    expect(turns).toEqual([
        { role: 'assistant', blocks: [{ type: 'text', text: 'a' }], regenerateAt: 0 },
    ]);
});

test('a file a tool produced is attached to the assistant turn', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'here you go' },
        {
            kind: 'tool_result',
            name: 'print_report',
            call_id: 'c1',
            result: '{"filename": "quote.pdf", "mimetype": "application/pdf", "attachment_id": 12}',
        },
    ]);
    expect(turns).toHaveLength(1);
    expect(turns[0].attachments).toEqual([
        { id: 12, filename: 'quote.pdf', mimetype: 'application/pdf' },
    ]);
});

test('the same produced file is attached to the turn only once', () => {
    const payload = '{"filename": "a.csv", "mimetype": "text/csv", "attachment_id": 4}';
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'x' },
        { kind: 'tool_result', name: 'export_records', call_id: 'c1', result: payload },
        {
            kind: 'tool_result',
            name: 'tool_load',
            call_id: 'c2',
            result: { call: { output: payload } },
        },
    ]);
    expect(turns[0].attachments).toHaveLength(1);
});

test('a tool result without a file leaves the turn unattached', () => {
    const turns = buildRenderedTurns([
        { kind: 'text', content: 'x' },
        {
            kind: 'tool_result',
            name: 'search_read',
            call_id: 'c1',
            result: '{"records": []}',
        },
    ]);
    expect(turns[0].attachments).toBe(undefined);
});
