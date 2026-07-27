const SAFE_SCHEME = /^(https?:|mailto:|#|\/)/i;
const SAFE_IMG_SCHEME = /^(https?:|data:image\/(png|jpeg|jpg|gif|webp);base64,|\/)/i;
const HTML_ESCAPE = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
};

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => HTML_ESCAPE[c]);
}

function highlightFence(code, lang) {
    const Prism = window.Prism;
    const safeLang = String(lang || '').toLowerCase();
    if (!Prism || !safeLang || !Prism.languages[safeLang]) {
        return escapeHtml(code);
    }
    try {
        return Prism.highlight(code, Prism.languages[safeLang], safeLang);
    } catch {
        return escapeHtml(code);
    }
}

function buildRenderer() {
    const md = window.markdownit({
        html: false,
        linkify: false,
        breaks: true,
    });
    md.validateLink = () => true;
    md.renderer.rules.fence = (tokens, idx) => {
        const token = tokens[idx];
        const rawLang = (token.info || '').trim().split(/\s+/)[0].toLowerCase();
        const body = highlightFence(token.content, rawLang);
        const langAttr = rawLang ? ` data-lang="${escapeHtml(rawLang)}"` : '';
        const langClass = rawLang ? ` class="language-${escapeHtml(rawLang)}"` : '';
        return (
            `<pre${langAttr}${langClass}>` +
            `<button type="button" class="mk_code_copy" aria-label="Copy code">Copy</button>` +
            `<code${langClass}>${body}</code>` +
            `</pre>`
        );
    };
    const TASK_RE = /^\[([ xX])\]\s+/;
    md.core.ruler.after('inline', 'muk_ai_task_lists', (state) => {
        const tokens = state.tokens;
        for (let i = 0; i < tokens.length; i++) {
            const tok = tokens[i];
            if (tok.type !== 'inline') {
                continue;
            }
            if (i < 2 || tokens[i - 2].type !== 'list_item_open') {
                continue;
            }
            const first = tok.children && tok.children[0];
            if (!first || first.type !== 'text') {
                continue;
            }
            const match = first.content.match(TASK_RE);
            if (!match) {
                continue;
            }
            first.content = first.content.slice(match[0].length);
            const checked = match[1].toLowerCase() === 'x';
            const box = new state.Token('html_inline', '', 0);
            box.content = `<input type="checkbox" disabled${
                checked ? ' checked' : ''
            }> `;
            tok.children.unshift(box);
            tokens[i - 2].attrJoin('class', 'mk_md_task');
        }
    });
    const LINKABLE_RE =
        /(\/web\/content\/\d+(?:\?[A-Za-z0-9_=&%.-]*)?)|\b([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+),(\d+)\b/g;
    md.core.ruler.after('inline', 'muk_ai_links', (state) => {
        const tokens = state.tokens;
        for (const tok of tokens) {
            if (tok.type !== 'inline' || !tok.children) {
                continue;
            }
            const newChildren = [];
            let linkDepth = 0;
            for (const child of tok.children) {
                if (child.type === 'link_open') {
                    linkDepth++;
                    newChildren.push(child);
                    continue;
                }
                if (child.type === 'link_close') {
                    linkDepth = Math.max(0, linkDepth - 1);
                    newChildren.push(child);
                    continue;
                }
                if (linkDepth > 0 || child.type !== 'text') {
                    newChildren.push(child);
                    continue;
                }
                const text = child.content;
                LINKABLE_RE.lastIndex = 0;
                let lastIndex = 0;
                let matched = false;
                let match;
                while ((match = LINKABLE_RE.exec(text)) !== null) {
                    matched = true;
                    const before = text.slice(lastIndex, match.index);
                    if (before) {
                        const t = new state.Token('text', '', 0);
                        t.content = before;
                        newChildren.push(t);
                    }
                    const [whole, fileUrl, model, id] = match;
                    const lo = new state.Token('link_open', 'a', 1);
                    lo.attrSet('href', fileUrl || `/odoo/${model}/${id}`);
                    lo.attrSet('class', fileUrl ? 'mk_file_link' : 'mk_record_link');
                    newChildren.push(lo);
                    const lt = new state.Token('text', '', 0);
                    lt.content = whole;
                    newChildren.push(lt);
                    newChildren.push(new state.Token('link_close', 'a', -1));
                    lastIndex = match.index + whole.length;
                }
                if (!matched) {
                    newChildren.push(child);
                    continue;
                }
                const tail = text.slice(lastIndex);
                if (tail) {
                    const t = new state.Token('text', '', 0);
                    t.content = tail;
                    newChildren.push(t);
                }
            }
            tok.children = newChildren;
        }
    });
    md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
        const token = tokens[idx];
        const hrefIdx = token.attrIndex('href');
        if (hrefIdx >= 0) {
            const href = String(token.attrs[hrefIdx][1]).trim();
            token.attrs[hrefIdx][1] = SAFE_SCHEME.test(href) ? href : '#';
        }
        token.attrSet('target', '_blank');
        token.attrSet('rel', 'noopener noreferrer');
        return self.renderToken(tokens, idx, options, env);
    };
    md.renderer.rules.image = (tokens, idx, options, env, self) => {
        const token = tokens[idx];
        const srcIdx = token.attrIndex('src');
        if (srcIdx >= 0) {
            const src = String(token.attrs[srcIdx][1]).trim();
            if (!SAFE_IMG_SCHEME.test(src)) {
                return '';
            }
        }
        token.attrSet('class', 'mk_md_image');
        return self.renderToken(tokens, idx, options, env);
    };
    return md;
}

let renderer = null;

/**
 * Render Markdown source to sanitized HTML, lazily building the renderer.
 * @param {string} source Markdown text
 * @returns {string} rendered HTML, or '' for empty input
 */
export function renderMarkdown(source) {
    if (!source) {
        return '';
    }
    renderer = renderer || buildRenderer();
    return renderer.render(String(source));
}

if (typeof window !== 'undefined' && !window.__mkCopyBound) {
    window.__mkCopyBound = true;
    document.addEventListener('click', (ev) => {
        const btn = ev.target.closest && ev.target.closest('.mk_code_copy');
        if (!btn) {
            return;
        }
        const pre = btn.closest('pre');
        const code = pre && pre.querySelector('code');
        if (!code) {
            return;
        }
        const reset = () => {
            btn.textContent = 'Copy';
            btn.classList.remove('mk_code_copy_done', 'mk_code_copy_fail');
        };
        navigator.clipboard
            .writeText(code.textContent)
            .then(() => {
                btn.textContent = 'Copied';
                btn.classList.add('mk_code_copy_done');
                setTimeout(reset, 1500);
            })
            .catch(() => {
                btn.textContent = 'Failed';
                btn.classList.add('mk_code_copy_fail');
                setTimeout(reset, 1500);
            });
    });
}
