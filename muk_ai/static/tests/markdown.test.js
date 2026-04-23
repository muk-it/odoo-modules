/** @odoo-module */

import { describe, expect, test } from '@odoo/hoot';

import { renderMarkdown } from '@muk_ai/core/markdown/markdown';

describe.current.tags('muk_ai');


test('neutralises javascript: scheme in links', () => {
    const out = renderMarkdown('[click](javascript:alert%281%29)');
    expect(out.includes('javascript:')).toBe(false);
    expect(out.includes('href="#"')).toBe(true);
});


test('emits <pre><code> blocks from fenced code', () => {
    const out = renderMarkdown('```\nconst x = 1;\n```');
    expect(out.includes('<pre')).toBe(true);
    expect(out.includes('<code')).toBe(true);
    expect(out.includes('const x = 1;')).toBe(true);
});


test('renders a markdown table into a <table>', () => {
    const out = renderMarkdown('| a | b |\n| - | - |\n| 1 | 2 |');
    expect(out.includes('<table')).toBe(true);
    expect(out.includes('<th>a</th>')).toBe(true);
    expect(out.includes('<td>1</td>')).toBe(true);
});


test('escapes raw HTML in bubble text so no injection occurs', () => {
    const out = renderMarkdown('hello <script>evil()</script>');
    expect(out.includes('<script>')).toBe(false);
    expect(out.includes('&lt;script&gt;')).toBe(true);
});
