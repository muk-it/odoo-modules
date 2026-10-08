import { expect, test } from '@odoo/hoot';

import {
    buildRenderedTurns,
    buildTurnItems,
    describeToolBlock,
    hiddenToolBlocks,
    isToolBlockHidden,
    toolBlockDecorators,
    toolResultFiles,
    turnBuilders,
} from '@muk_ai/core/session/turns';
import { defineAIModels, getChat } from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const call = (id, name = 'search_read') => ({
    kind: 'tool_call',
    call_id: id,
    name,
    arguments: '{}',
});
const result = (id, value = '{"ok": true}', extra = {}) => ({
    kind: 'tool_result',
    call_id: id,
    result: value,
    ...extra,
});

test('the event log folds into user, assistant, command and compaction turns', async () => {
    await getChat();
    const turns = buildRenderedTurns([
        { kind: 'user_message', content: 'Hi', event_id: 1, at: '2026-01-01T10:00:00' },
        call('c1'),
        result('c1'),
        { kind: 'text', content: 'One', event_id: 4 },
        { kind: 'text', content: 'Two', event_id: 5 },
        { kind: 'ask_user', text: 'Sure?', call_id: 'c2', resolution: 'yesno' },
        { kind: 'answer', answer: 'Yes', event_id: 7 },
        { kind: 'agent_switched', from_agent_name: 'General', agent_name: 'Analyst' },
        { kind: 'command', name: '/compact', summary: 'Short', original_messages: 6 },
        { kind: 'compact_progress', event_id: 9, state: 'done', auto: true },
        { kind: 'text', content: 'After', event_id: 10 },
    ]);
    expect(turns.map((turn) => turn.role)).toEqual([
        'user',
        'assistant',
        'user',
        'command',
        'command',
        'compact_progress',
        'assistant',
    ]);
    expect(turns[0]).toMatchObject({
        text: 'Hi',
        eventId: 1,
        at: '2026-01-01T10:00:00',
    });
    expect(turns[1].blocks.map((block) => block.type)).toEqual(['tool', 'text', 'ask']);
    expect(turns[1].blocks[1].text).toBe('One\n\nTwo');
    expect(turns[1].blocks[0].result).toBe('{"ok": true}');
    expect(turns[2].text).toBe('Yes');
    expect(String(turns[3].message)).toBe('General → Analyst');
    expect(turns.slice(0, 5).every((turn) => turn.inHistory)).toBe(true);
    expect(turns[5].inHistory).toBe(undefined);
    expect([turns[1].regenerateAt, turns[6].regenerateAt]).toEqual([undefined, 0]);
});

test('a result without its call still draws, sources and files collect once per turn', () => {
    const source = { id: 'web:a', type: 'web', url: 'https://a.example' };
    const [turn] = buildRenderedTurns([
        result('lost', 'x', { name: 'web_search', sources: [source] }),
        call('c1', 'export_records'),
        result('c1', JSON.stringify({ attachment_id: 12, filename: 'x.xlsx' }), {
            sources: [source],
        }),
    ]);
    expect(turn.blocks.map((block) => block.callId)).toEqual(['lost', 'c1']);
    expect(turn.sources).toEqual([source]);
    expect(turn.attachments).toEqual([{ id: 12, filename: 'x.xlsx', mimetype: '' }]);
});

test('an addon draws the event kinds it builds turns for', () => {
    turnBuilders.add('plan', (entry) =>
        entry.steps.length ? { role: 'plan', steps: entry.steps } : null,
    );
    const turns = buildRenderedTurns([
        { kind: 'plan', steps: ['a'], event_id: 3 },
        { kind: 'plan', steps: [] },
        { kind: 'unknown_kind' },
    ]);
    expect(turns).toEqual([{ role: 'plan', steps: ['a'], eventId: 3 }]);
});

test('files are found at any depth of a tool result, once each', () => {
    const files = toolResultFiles(
        JSON.stringify({
            content: [
                { attachment_id: 1, filename: 'a.pdf', mimetype: 'application/pdf' },
            ],
            nested: JSON.stringify({ attachment_id: 2 }),
            again: { attachment_id: 1 },
        }),
    );
    expect(files).toEqual([
        { id: 1, filename: 'a.pdf', mimetype: 'application/pdf' },
        { id: 2, filename: 'download', mimetype: '' },
    ]);
    expect(toolResultFiles('plain text')).toEqual([]);
});

test('decorators describe a tool card from its live arguments and result', () => {
    toolBlockDecorators.add('memory', (block) => {
        if (block.name === 'remember') {
            describeToolBlock(block, {
                kind: 'nav',
                label: ({ args }) => `Remember ${args.fact}`,
                band: ({ result, pending }) => (pending ? 'saving' : result.saved),
            });
        }
    });
    const [turn] = buildRenderedTurns([
        {
            kind: 'tool_call',
            call_id: 'c1',
            name: 'remember',
            arguments: '{"fact": "tea"}',
        },
    ]);
    const block = turn.blocks[0];
    expect([block.kind, block.label, block.band]).toEqual([
        'nav',
        'Remember tea',
        'saving',
    ]);
    block.result = '{"saved": "kept"}';
    expect(block.band).toBe('kept');
});

test('a tool card stays out while a question, a client action or another card shows its call', () => {
    hiddenToolBlocks.add('delegation', (block) => block.name === 'delegate');
    const turn = { blocks: [{ type: 'ask', callId: 'c2' }] };
    const actions = {
        kind: 'client_action',
        actions: [
            { call_id: 'c5', name: 'adjust_search', done: false },
            { call_id: 'c6', name: 'adjust_search', done: true },
        ],
    };
    for (const [block, pending, hidden] of [
        [{ name: 'delegate', callId: 'c9', result: 'done' }, null, true],
        [{ name: 'ask_user', callId: 'c2', result: null }, null, true],
        [{ name: 'other', callId: 'c3', result: null }, { call_id: 'c3' }, true],
        [{ name: 'other', callId: 'c3', result: 'ok' }, { call_id: 'c3' }, false],
        [{ name: 'other', callId: 'c4', result: null }, null, false],
        [{ name: 'adjust_search', callId: 'c5', result: null }, actions, true],
        [{ name: 'adjust_search', callId: 'c6', result: null }, actions, false],
    ]) {
        expect(isToolBlockHidden(block, turn, pending)).toBe(hidden);
    }
});

test('consecutive visible tool calls cluster into one group item', () => {
    const blocks = [
        { type: 'tool', callId: 'a' },
        { type: 'tool', callId: 'b' },
        { type: 'text', text: 'x' },
        { type: 'tool', callId: 'c' },
        { type: 'tool', callId: 'hidden' },
    ];
    const items = buildTurnItems(blocks, (block) => block.callId === 'hidden');
    expect(items.map((item) => [item.type, item.key])).toEqual([
        ['group', 'g-0'],
        ['text', 't-2'],
        ['tool', 't-3'],
        ['tool', 't-4'],
    ]);
    expect(items[0].tools.map((tool) => tool.block.callId)).toEqual(['a', 'b']);
});
