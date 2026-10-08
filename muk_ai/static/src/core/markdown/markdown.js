import { htmlEscape, markup, signal } from '@odoo/owl';

import { loadBundle } from '@web/core/assets';
import { cookie } from '@web/core/browser/cookie';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

const SAFE_SCHEME = /^(https?:|mailto:|#|\/)/i;
const SAFE_IMG_SCHEME = /^(https?:|data:image\/(png|jpeg|jpg|gif|webp);base64,|\/)/i;
const RECORD_HREF = /^([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+),(\d+)$/;
const LINKABLE =
    /(\/web\/content\/\d+(?:\?[A-Za-z0-9_=&%.-]*)?)|\b([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+),(\d+)\b/g;
const TASK = /^\[([ xX])\]\s+/;
const CACHE_SIZE = 400;

/**
 * Registry of markdown-it plugins applied after the core rules, as
 * `(md) => void`. They are read once, when the renderer is first built.
 */
export const markdownPlugins = registry.category('muk_ai.markdown_plugins');

const version = signal(0);
const cache = new Map();
let loading = null;
let renderer = null;

markdownPlugins.addEventListener('UPDATE', () => {
    renderer = null;
    cache.clear();
});

/**
 * Load markdown-it and the Prism theme matching the colour scheme, once.
 * @returns {Promise<void>} resolved when both are available
 */
export function loadMarkdown() {
    const prism = `html_editor.assets_prism${cookie.get('color_scheme') === 'dark' ? '_dark' : ''}`;
    loading ||= Promise.all([
        window.markdownit || loadBundle('muk_ai.assets_markdown'),
        window.Prism || loadBundle(prism),
    ])
        .catch(() => {})
        .then(() => {
            cache.clear();
            version.set(version() + 1);
        });
    return loading;
}

/**
 * Highlight source code with Prism when the language is known.
 * @param {string} code the source
 * @param {string} lang the language name
 * @returns {string|null} highlighted HTML, null when Prism cannot do it
 */
export function highlightCode(code, lang) {
    const grammar = window.Prism?.languages[lang];
    return grammar ? window.Prism.highlight(code, grammar, lang) : null;
}

/**
 * Turn `/web/content/<id>` paths and `model,id` pairs in plain text into links.
 * @param {object} state the markdown-it core state
 */
function linkify(state) {
    for (const token of state.tokens) {
        if (token.type !== 'inline' || !token.children) {
            continue;
        }
        const children = [];
        let depth = 0;
        for (const child of token.children) {
            depth +=
                child.type === 'link_open' ? 1 : child.type === 'link_close' ? -1 : 0;
            if (depth > 0 || child.type !== 'text') {
                children.push(child);
                continue;
            }
            let last = 0;
            const text = (content) => {
                if (content) {
                    children.push(
                        Object.assign(new state.Token('text', '', 0), { content }),
                    );
                }
            };
            for (const match of child.content.matchAll(LINKABLE)) {
                const [whole, file, model, id] = match;
                text(child.content.slice(last, match.index));
                const open = new state.Token('link_open', 'a', 1);
                open.attrSet('href', file || `/odoo/${model}/${id}`);
                open.attrSet('class', file ? 'mk_file_link' : 'mk_record_link');
                children.push(open);
                text(whole);
                children.push(new state.Token('link_close', 'a', -1));
                last = match.index + whole.length;
            }
            text(child.content.slice(last));
        }
        token.children = children;
    }
}

/**
 * Draw `[ ]` and `[x]` list items as disabled checkboxes.
 * @param {object} state the markdown-it core state
 */
function taskLists(state) {
    state.tokens.forEach((token, index) => {
        const first = token.children?.[0];
        const match = first?.type === 'text' && first.content.match(TASK);
        if (
            token.type !== 'inline' ||
            state.tokens[index - 2]?.type !== 'list_item_open'
        ) {
            return;
        }
        if (match) {
            first.content = first.content.slice(match[0].length);
            const box = new state.Token('html_inline', '', 0);
            box.content = `<input type="checkbox" disabled${match[1] === ' ' ? '' : ' checked'}> `;
            token.children.unshift(box);
            state.tokens[index - 2].attrJoin('class', 'mk_md_task');
        }
    });
}

/**
 * Build the markdown-it renderer with the safe link, image and code rules.
 * @returns {object} the renderer
 */
function buildRenderer() {
    const md = window.markdownit({ html: false, linkify: false, breaks: true });
    md.validateLink = () => true;
    md.renderer.rules.fence = (tokens, index) => {
        const lang = (tokens[index].info || '').trim().split(/\s+/)[0].toLowerCase();
        const code = tokens[index].content;
        const body = (lang && highlightCode(code, lang)) || htmlEscape(code);
        const cls = lang ? ` class="language-${htmlEscape(lang)}"` : '';
        const data = lang ? ` data-lang="${htmlEscape(lang)}"` : '';
        const copy = `<button type="button" class="mk_code_copy">${_t('Copy')}</button>`;
        return `<pre${data}${cls}>${copy}<code${cls}>${body}</code></pre>`;
    };
    md.renderer.rules.table_open = () => '<div class="mk_md_table"><table>';
    md.renderer.rules.table_close = () => '</table></div>';
    md.core.ruler.after('inline', 'muk_ai_task_lists', taskLists);
    md.core.ruler.after('inline', 'muk_ai_links', linkify);
    md.renderer.rules.link_open = (tokens, index, options, env, self) => {
        const token = tokens[index];
        const href = String(token.attrGet('href') || '').trim();
        const record = RECORD_HREF.exec(href);
        if (record) {
            token.attrSet('href', `/odoo/${record[1]}/${record[2]}`);
            token.attrJoin('class', 'mk_record_link');
        } else {
            token.attrSet('href', SAFE_SCHEME.test(href) ? href : '#');
        }
        token.attrSet('target', '_blank');
        token.attrSet('rel', 'noopener noreferrer');
        return self.renderToken(tokens, index, options);
    };
    md.renderer.rules.image = (tokens, index, options, env, self) => {
        const token = tokens[index];
        if (!SAFE_IMG_SCHEME.test(String(token.attrGet('src') || '').trim())) {
            return '';
        }
        token.attrSet('class', 'mk_md_image');
        return self.renderToken(tokens, index, options);
    };
    for (const plugin of markdownPlugins.getAll()) {
        plugin(md);
    }
    return md;
}

/**
 * Render Markdown to sanitized HTML, loading the renderer on first use.
 * @param {string} source the Markdown text
 * @returns {object|string} the rendered markup, empty for empty input
 */
export function renderMarkdown(source) {
    void version();
    if (!source) {
        return '';
    }
    const text = String(source);
    if (!window.markdownit) {
        loadMarkdown();
        return markup`<p class="text-prewrap">${text}</p>`;
    }
    let html = cache.get(text);
    if (html === undefined) {
        renderer ||= buildRenderer();
        html = markup(renderer.render(text));
        if (cache.size >= CACHE_SIZE) {
            cache.delete(cache.keys().next().value);
        }
    }
    cache.delete(text);
    cache.set(text, html);
    return html;
}

/**
 * Copy the code block a copy button sits in, flashing the outcome on it.
 * @param {HTMLElement} button the copy button
 */
export function copyCode(button) {
    const label = (text, cls) => {
        button.textContent = text;
        button.classList.toggle(cls, true);
        setTimeout(() => {
            button.textContent = _t('Copy');
            button.classList.remove(cls);
        }, 1500);
    };
    navigator.clipboard.writeText(button.nextElementSibling?.textContent || '').then(
        () => label(_t('Copied'), 'mk_code_copy_done'),
        () => label(_t('Failed'), 'mk_code_copy_fail'),
    );
}
