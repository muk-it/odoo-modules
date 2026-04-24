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


test('returns empty string for empty or null source', () => {
    expect(renderMarkdown('')).toBe('');
    expect(renderMarkdown(null)).toBe('');
    expect(renderMarkdown(undefined)).toBe('');
});


test('fenced block with language gets data-lang + language-* class', () => {
    const out = renderMarkdown('```json\n{"a": 1}\n```');
    expect(out).toMatch(/data-lang="json"/);
    expect(out).toMatch(/language-json/);
});


test('fenced block without language falls back to escapeHtml', () => {
    const out = renderMarkdown('```\n<b>raw</b>\n```');
    expect(out.includes('<b>raw</b>')).toBe(false);
    expect(out.includes('&lt;b&gt;')).toBe(true);
});


test('fenced block embeds the copy button', () => {
    const out = renderMarkdown('```\nhello\n```');
    expect(out).toMatch(/class="mk_code_copy"/);
    expect(out).toMatch(/Copy/);
});


test('task list marker [ ] becomes unchecked checkbox input', () => {
    const out = renderMarkdown('- [ ] todo one\n- [ ] todo two');
    expect(out).toMatch(/type="checkbox"/);
    expect(out).toMatch(/mk_md_task/);
    expect(out.match(/checkbox[^>]*checked/)).toBe(null);
});


test('task list marker [x] becomes checked checkbox input', () => {
    const out = renderMarkdown('- [x] done');
    expect(out).toMatch(/checkbox[^>]*checked/);
});


test('links get target _blank and rel noopener noreferrer', () => {
    const out = renderMarkdown('[docs](https://example.com)');
    expect(out).toMatch(/target="_blank"/);
    expect(out).toMatch(/rel="noopener noreferrer"/);
    expect(out).toMatch(/href="https:\/\/example\.com"/);
});


test('mailto and fragment links are preserved', () => {
    expect(renderMarkdown('[mail](mailto:hi@x.com)')).toMatch(/href="mailto:hi@x\.com"/);
    expect(renderMarkdown('[frag](#anchor)')).toMatch(/href="#anchor"/);
});


test('image with safe https:// src renders', () => {
    const out = renderMarkdown('![alt](https://example.com/p.png)');
    expect(out).toMatch(/<img/);
    expect(out).toMatch(/src="https:\/\/example\.com\/p\.png"/);
});


test('image with data:image base64 src renders', () => {
    const out = renderMarkdown('![g](data:image/png;base64,AAAA)');
    expect(out).toMatch(/src="data:image\/png;base64,AAAA"/);
});


test('image with non-safe src is stripped', () => {
    const out = renderMarkdown('![g](javascript:alert(1))');
    expect(out.includes('<img')).toBe(false);
});


test('clicking mk_code_copy button invokes navigator.clipboard.writeText', async () => {
    const original = navigator.clipboard;
    const writes = [];
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: (t) => { writes.push(t); return Promise.resolve(); } },
    });
    try {
        const host = document.createElement('div');
        host.innerHTML = '<pre><button class="mk_code_copy">Copy</button><code>hello()</code></pre>';
        document.body.appendChild(host);
        host.querySelector('.mk_code_copy').click();
        await new Promise((r) => setTimeout(r, 0));
        expect(writes).toEqual(['hello()']);
        host.remove();
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true, value: original,
        });
    }
});


test('clicking outside mk_code_copy does not trigger clipboard', async () => {
    const original = navigator.clipboard;
    const writes = [];
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: (t) => { writes.push(t); return Promise.resolve(); } },
    });
    try {
        const host = document.createElement('div');
        host.innerHTML = '<pre><code>x</code></pre>';
        document.body.appendChild(host);
        host.querySelector('code').click();
        expect(writes).toEqual([]);
        host.remove();
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true, value: original,
        });
    }
});
