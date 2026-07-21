import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { mountWithCleanup, patchTranslations } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { collectSources } from '@muk_ai/chat/artifacts/types/sources_type';
import { SourceList } from '@muk_ai/chat/artifacts/types/sources_tab';
import { buildRenderedTurns } from '@muk_ai/chat/session/turns';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();

function makeRecordSources(count) {
    return Array.from({ length: count }, (_, i) => ({
        id: `record:res.partner,${i + 1}`,
        type: 'record',
        res_model: 'res.partner',
        res_id: i + 1,
        display_name: `Partner ${i + 1}`,
        href: `/odoo/res.partner/${i + 1}`,
    }));
}

function webResult(url, title) {
    return {
        kind: 'tool_result',
        name: 'web_fetch',
        sources: [
            {
                id: `web:${url}`,
                type: 'web',
                url,
                title,
                domain: 'example.com',
            },
        ],
    };
}

function recordResult(model, id, displayName) {
    return {
        kind: 'tool_result',
        name: 'read_records',
        sources: [
            {
                id: `record:${model},${id}`,
                type: 'record',
                res_model: model,
                res_id: id,
                display_name: displayName,
                href: `/odoo/${model}/${id}`,
            },
        ],
    };
}

test('collectSources unions web and record sources in order', () => {
    const items = collectSources({
        events: [
            { kind: 'user_message', content: 'hi' },
            webResult('https://example.com/a', 'A'),
            recordResult('res.partner', 7, 'Acme'),
        ],
    });
    expect(items.map((s) => s.id)).toEqual([
        'web:https://example.com/a',
        'record:res.partner,7',
    ]);
    expect(items[0].type).toBe('web');
    expect(items[1].href).toBe('/odoo/res.partner/7');
});

test('collectSources dedupes repeated sources by id', () => {
    const items = collectSources({
        events: [
            webResult('https://example.com/a', 'A'),
            webResult('https://example.com/a', 'A again'),
            recordResult('res.partner', 7, 'Acme'),
        ],
    });
    expect(items.map((s) => s.id)).toEqual([
        'web:https://example.com/a',
        'record:res.partner,7',
    ]);
});

test('collectSources ignores tool results without sources', () => {
    const items = collectSources({
        events: [
            { kind: 'tool_result', name: 'search_count', result: '{"count": 3}' },
            { kind: 'text', content: 'no sources here' },
        ],
    });
    expect(items).toEqual([]);
});

test('collectSources returns empty for missing state', () => {
    expect(collectSources(null)).toEqual([]);
    expect(collectSources({})).toEqual([]);
});

test('buildRenderedTurns attaches deduped sources to the assistant turn', () => {
    const turns = buildRenderedTurns([
        { kind: 'user_message', content: 'go' },
        { kind: 'tool_call', name: 'read_records', call_id: 'c1' },
        recordResult('res.partner', 7, 'Acme'),
        { kind: 'tool_call', name: 'web_fetch', call_id: 'c2' },
        webResult('https://example.com/a', 'A'),
        webResult('https://example.com/a', 'A dup'),
        { kind: 'text', content: 'Done.' },
    ]);
    const assistant = turns.find((t) => t.role === 'assistant');
    expect(assistant.sources.map((s) => s.id)).toEqual([
        'record:res.partner,7',
        'web:https://example.com/a',
    ]);
});

test('buildRenderedTurns leaves sources unset for a turn with none', () => {
    const turns = buildRenderedTurns([
        { kind: 'user_message', content: 'hi' },
        { kind: 'tool_call', name: 'search_read', call_id: 'c1' },
        { kind: 'tool_result', name: 'search_read', call_id: 'c1', result: '[]' },
        { kind: 'text', content: 'None.' },
    ]);
    const assistant = turns.find((t) => t.role === 'assistant');
    expect(assistant.sources).toBe(undefined);
});

test('SourceList caps the display and reveals the rest on +N more', async () => {
    await mountWithCleanup(SourceList, {
        props: { sources: makeRecordSources(12), cap: 8 },
    });
    expect(queryAll('.mk_source_card').length).toBe(8);
    const more = queryFirst('.mk_sources_more_btn');
    expect(more.textContent).toInclude('4 more');
    await click(more);
    await animationFrame();
    expect(queryAll('.mk_source_card').length).toBe(12);
});

test('SourceList shows no +N more when within the cap', async () => {
    await mountWithCleanup(SourceList, {
        props: { sources: makeRecordSources(3), cap: 8 },
    });
    expect(queryAll('.mk_source_card').length).toBe(3);
    expect(queryFirst('.mk_sources_more_btn')).toBe(null);
});

test('buildRenderedTurns scopes sources per turn', () => {
    const turns = buildRenderedTurns([
        { kind: 'user_message', content: 'first' },
        { kind: 'tool_call', name: 'web_fetch', call_id: 'c1' },
        webResult('https://a.test', 'A'),
        { kind: 'text', content: 'one' },
        { kind: 'user_message', content: 'second' },
        { kind: 'tool_call', name: 'web_fetch', call_id: 'c2' },
        webResult('https://b.test', 'B'),
        { kind: 'text', content: 'two' },
    ]);
    const assistants = turns.filter((t) => t.role === 'assistant');
    expect(assistants[0].sources.map((s) => s.id)).toEqual(['web:https://a.test']);
    expect(assistants[1].sources.map((s) => s.id)).toEqual(['web:https://b.test']);
});
