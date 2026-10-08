import { after, expect, test } from '@odoo/hoot';
import { patch } from '@web/core/utils/patch';

import {
    copyCode,
    markdownPlugins,
    renderMarkdown,
} from '@muk_ai/core/markdown/markdown';
import { defineAIModels, getChat } from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const html = (source) => String(renderMarkdown(source));

test('markdown renders headings, emphasis, lists, tables, task lists and line breaks', () => {
    for (const [source, expected] of [
        ['# Title', '<h1>Title</h1>'],
        ['**bold** and _it_', '<strong>bold</strong> and <em>it</em>'],
        ['- a\n- b', '<li>a</li>'],
        ['| a |\n|---|\n| 1 |', '<td>1</td>'],
        ['| a |\n|---|\n| 1 |', '<div class="mk_md_table"><table>'],
        [
            '- [x] done\n- [ ] open',
            'class="mk_md_task"><input type="checkbox" disabled checked> done',
        ],
        ['one\ntwo', 'one<br>'],
    ]) {
        expect(html(source)).toInclude(expected);
    }
    expect(html('')).toBe('');
});

test('unsafe links, images and raw HTML are neutralised', () => {
    for (const [source, forbidden] of [
        ['[x](javascript:alert(1))', 'javascript:'],
        ['<script>alert(1)</script>', '<script>'],
        ['![x](javascript:alert(1))', '<img'],
        ['![x](data:text/html;base64,AAAA)', '<img'],
    ]) {
        expect(html(source)).not.toInclude(forbidden);
    }
    expect(html('[x](https://odoo.com)')).toInclude(
        'target="_blank" rel="noopener noreferrer"',
    );
    expect(html('![x](/web/image/4)')).toInclude('class="mk_md_image"');
});

test('record references and stored files turn into links', () => {
    for (const [source, link] of [
        [
            'see res.partner,7 now',
            '<a href="/odoo/res.partner/7" class="mk_record_link"',
        ],
        ['[the deal](crm.lead,3)', 'href="/odoo/crm.lead/3"'],
        [
            'get /web/content/12?download=true',
            '<a href="/web/content/12?download=true" class="mk_file_link"',
        ],
        ['`res.partner,7` stays code', '<code>res.partner,7</code>'],
    ]) {
        expect(html(source)).toInclude(link);
    }
    expect(html('[already](https://x.example) res.partner')).not.toInclude(
        'mk_record_link',
    );
});

test('a code block carries its language and a copy button that copies it', async () => {
    await getChat();
    const block = html('```python\nprint(1)\n```');
    expect(block).toInclude(
        '<pre data-lang="python" class="language-python"><button type="button" class="mk_code_copy">Copy</button>',
    );
    const root = document.createElement('div');
    root.innerHTML = block;
    let copied = '';
    patch(navigator.clipboard, { writeText: async (text) => (copied = text) });
    copyCode(root.querySelector('.mk_code_copy'));
    await Promise.resolve();
    await Promise.resolve();
    expect(copied).toBe('print(1)\n');
    expect(root.querySelector('.mk_code_copy').textContent).toBe('Copied');
});

test('a markdown plugin registered by an addon extends the renderer', () => {
    after(() => markdownPlugins.remove('shout'));
    markdownPlugins.add('shout', (md) => {
        md.core.ruler.push('shout', (state) => {
            for (const token of state.tokens) {
                token.children?.forEach(
                    (child) => (child.content = child.content.toUpperCase()),
                );
            }
        });
    });
    expect(html('quiet please')).toInclude('QUIET PLEASE');
});
