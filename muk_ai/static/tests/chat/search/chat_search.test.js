import { describe, expect, test } from '@odoo/hoot';

import {
    buildIndex,
    entryFirstMatchIndex,
    escapeAndHighlight,
    findMatches,
    highlightHtml,
} from '@muk_ai/chat/search/search_index';

describe.current.tags('muk_ai');

function asString(html) {
    if (html == null) return '';
    if (typeof html === 'string') return html;
    if (html.toString) return html.toString();
    return String(html);
}

test('buildIndex picks user text and assistant text-blocks only', () => {
    const turns = [
        { role: 'user', text: 'hello world' },
        {
            role: 'assistant',
            blocks: [
                { type: 'text', text: 'hello there' },
                { type: 'tool', name: 'sql', arguments: 'SELECT hello' },
                { type: 'text', text: 'second hello' },
            ],
        },
        { role: 'command', name: '/clear' },
    ];
    const idx = buildIndex(turns);
    expect(idx.length).toBe(3);
    expect(idx[0].anchorId).toBe('mk_msg_0_user');
    expect(idx[1].anchorId).toBe('mk_msg_1_0');
    expect(idx[2].anchorId).toBe('mk_msg_1_2');
});

test('findMatches counts every occurrence case-insensitively', () => {
    const turns = [
        { role: 'user', text: 'Hello hello HELLO' },
        { role: 'assistant', blocks: [{ type: 'text', text: 'Hello world' }] },
    ];
    const matches = findMatches(buildIndex(turns), 'hello');
    expect(matches.length).toBe(4);
});

test('findMatches ignores tool/ask content (scope)', () => {
    const turns = [
        {
            role: 'assistant',
            blocks: [
                { type: 'tool', name: 'hello_tool', arguments: 'hello' },
                { type: 'ask', text: 'should I hello?', callId: 'c1' },
            ],
        },
    ];
    const matches = findMatches(buildIndex(turns), 'hello');
    expect(matches.length).toBe(0);
});

test('escapeAndHighlight HTML-escapes input then wraps the active match', () => {
    const out = asString(escapeAndHighlight('a<b>hello</b>c hello', 'hello', 1, 0));
    expect(out.includes('&lt;b&gt;')).toBe(true);
    expect(out.includes('mk_search_hit_active')).toBe(true);
    expect(out.includes('mk_search_hit')).toBe(true);
    const active = (out.match(/mk_search_hit_active/g) || []).length;
    expect(active).toBe(1);
});

test('highlightHtml preserves anchor href and skips script/style/mark', () => {
    const html =
        '<p>hello <a href="https://x">hello</a></p>' +
        '<script>var hello = 1;</script>' +
        '<mark class="mk_search_hit">hello</mark>';
    const out = asString(highlightHtml(html, 'hello', 0, 0));
    expect(out.includes('href="https://x"')).toBe(true);
    expect(out.includes('var hello = 1;')).toBe(true);
    const total =
        (out.match(/mk_search_hit(?!_active)/g) || []).length +
        (out.match(/mk_search_hit_active/g) || []).length;
    expect(total).toBeGreaterThan(0);
    expect(total).toBeLessThan(5);
});

test('entryFirstMatchIndex returns -1 when entry has no matches', () => {
    const turns = [
        { role: 'user', text: 'hello' },
        { role: 'assistant', blocks: [{ type: 'text', text: 'no match here' }] },
    ];
    const idx = buildIndex(turns);
    const matches = findMatches(idx, 'hello');
    expect(entryFirstMatchIndex(matches, idx[0])).toBe(0);
    expect(entryFirstMatchIndex(matches, idx[1])).toBe(-1);
});

test('entryFirstMatchIndex matches across separate buildIndex calls (anchorId fallback)', () => {
    const turns = [
        { role: 'user', text: 'hello' },
        { role: 'assistant', blocks: [{ type: 'text', text: 'hello world' }] },
    ];
    const idxA = buildIndex(turns);
    const idxB = buildIndex(turns);
    const matchesA = findMatches(idxA, 'hello');
    expect(idxA[0]).not.toBe(idxB[0]);
    expect(entryFirstMatchIndex(matchesA, idxB[0])).toBe(0);
    expect(entryFirstMatchIndex(matchesA, idxB[1])).toBe(1);
});

test('only the activeMatchIdx-th hit gets the active class', () => {
    const turns = [{ role: 'user', text: 'foo foo foo' }];
    const idx = buildIndex(turns);
    const matches = findMatches(idx, 'foo');
    expect(matches.length).toBe(3);
    const active = 1;
    const html = asString(escapeAndHighlight('foo foo foo', 'foo', active, 0));
    const activeCount = (html.match(/mk_search_hit_active/g) || []).length;
    expect(activeCount).toBe(1);
    const totalHits = (html.match(/mk_search_hit(?!_active)/g) || []).length;
    expect(totalHits).toBe(2);
});
