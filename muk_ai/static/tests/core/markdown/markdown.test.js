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
    expect(renderMarkdown('[mail](mailto:hi@x.com)')).toMatch(
        /href="mailto:hi@x\.com"/,
    );
    expect(renderMarkdown('[frag](#anchor)')).toMatch(/href="#anchor"/);
});

test('image with safe https:// src renders', () => {
    const out = renderMarkdown('![alt](https://example.com/p.png)');
    expect(out).toMatch(/<img/);
    expect(out).toMatch(/src="https:\/\/example\.com\/p\.png"/);
});

test('images carry the mk_md_image class the click-to-preview handler targets', () => {
    expect(renderMarkdown('![alt](https://example.com/p.png)')).toMatch(
        /class="mk_md_image"/,
    );
    expect(renderMarkdown('![g](/web/image/1032)')).toMatch(/class="mk_md_image"/);
});

test('image with data:image base64 src renders', () => {
    const out = renderMarkdown('![g](data:image/png;base64,AAAA)');
    expect(out).toMatch(/src="data:image\/png;base64,AAAA"/);
});

test('image with non-safe src is stripped', () => {
    const out = renderMarkdown('![g](javascript:alert(1))');
    expect(out.includes('<img')).toBe(false);
});

/**
 * Collect the href of every anchor in a rendered HTML string, in document order.
 * @param {string} html rendered markdown
 * @returns {string[]} the href values
 */
function hrefsOf(html) {
    return [...html.matchAll(/href="([^"]+)"/g)].map((match) => match[1]);
}

test('a bare model,id reference becomes a backend record link', () => {
    const out = renderMarkdown('Check res.partner,5 for details');
    expect(
        out.includes(
            '<a href="/odoo/res.partner/5" class="mk_record_link" ' +
                'target="_blank" rel="noopener noreferrer">res.partner,5</a>',
        ),
    ).toBe(true);
});

test('every reference in a sentence is linked and the surrounding text kept', () => {
    const out = renderMarkdown('A res.partner,5 and sale.order,12 B');
    expect(hrefsOf(out)).toEqual(['/odoo/res.partner/5', '/odoo/sale.order/12']);
    expect(out).toMatch(/A <a/);
    expect(out).toMatch(/<\/a> and <a/);
    expect(out).toMatch(/<\/a> B/);
});

test('a dotted model with several segments is linked too', () => {
    const out = renderMarkdown('see mail.activity.type,3');
    expect(hrefsOf(out)).toEqual(['/odoo/mail.activity.type/3']);
});

test('a reference already inside a link is not linked twice', () => {
    const out = renderMarkdown('[res.partner,5](https://example.com)');
    expect(hrefsOf(out)).toEqual(['https://example.com']);
    expect(out.includes('mk_record_link')).toBe(false);
});

test('a reference inside code is left verbatim', () => {
    expect(renderMarkdown('use `res.partner,5` here').includes('mk_record_link')).toBe(
        false,
    );
    expect(renderMarkdown('```\nres.partner,5\n```').includes('mk_record_link')).toBe(
        false,
    );
});

test('text that only looks like a reference stays plain', () => {
    const out = renderMarkdown('partner,5 and res.partner,x and Res.Partner,5');
    expect(out.includes('mk_record_link')).toBe(false);
    expect(hrefsOf(out)).toEqual([]);
});

test('clicking mk_code_copy button invokes navigator.clipboard.writeText', async () => {
    const original = navigator.clipboard;
    const writes = [];
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: (t) => {
                writes.push(t);
                return Promise.resolve();
            },
        },
    });
    try {
        const host = document.createElement('div');
        host.innerHTML =
            '<pre><button class="mk_code_copy">Copy</button><code>hello()</code></pre>';
        document.body.appendChild(host);
        host.querySelector('.mk_code_copy').click();
        await new Promise((r) => setTimeout(r, 0));
        expect(writes).toEqual(['hello()']);
        host.remove();
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: original,
        });
    }
});

test('clicking outside mk_code_copy does not trigger clipboard', async () => {
    const original = navigator.clipboard;
    const writes = [];
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: (t) => {
                writes.push(t);
                return Promise.resolve();
            },
        },
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
            configurable: true,
            value: original,
        });
    }
});

test('a bare download url a tool returned becomes a clickable link', () => {
    const out = renderMarkdown('Download: /web/content/45604?download=1');
    expect(
        out.includes(
            '<a href="/web/content/45604?download=1" class="mk_file_link" ' +
                'target="_blank" rel="noopener noreferrer">/web/content/45604?download=1</a>',
        ),
    ).toBe(true);
});

test('a download url already inside a markdown link is not linked twice', () => {
    const out = renderMarkdown('[Download](/web/content/42?download=1)');
    expect(hrefsOf(out)).toEqual(['/web/content/42?download=1']);
    expect(out.includes('mk_file_link')).toBe(false);
});

test('a download url inside code stays verbatim', () => {
    const out = renderMarkdown('`/web/content/42?download=1`');
    expect(out.includes('mk_file_link')).toBe(false);
});

test('text after a download url is preserved', () => {
    const out = renderMarkdown('Get /web/content/7 now');
    expect(out.includes('mk_file_link')).toBe(true);
    expect(out.includes(' now')).toBe(true);
});
