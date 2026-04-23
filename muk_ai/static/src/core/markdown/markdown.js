/** @odoo-module */

const HTML_ESCAPE = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const SAFE_SCHEME = /^(https?:|mailto:|#|\/)/i;

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => HTML_ESCAPE[c]);
}

function safeHref(href) {
    const trimmed = String(href).trim();
    return SAFE_SCHEME.test(trimmed) ? escapeHtml(trimmed) : '#';
}

function applyInline(text) {
    return text
        .replace(/`([^`\n]+)`/g, (_, code) => `<code>${code}</code>`)
        .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
        .replace(/(^|[^\*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) =>
            `<a href="${safeHref(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`,
        );
}

function highlightCode(code, lang) {
    const Prism = typeof window !== 'undefined' ? window.Prism : undefined;
    if (!Prism || !lang) {
        return escapeHtml(code);
    }
    const grammar = Prism.languages[lang.toLowerCase()];
    if (!grammar) {
        return escapeHtml(code);
    }
    try {
        return Prism.highlight(code, grammar, lang);
    } catch (_err) {
        return escapeHtml(code);
    }
}

function renderTable(rows) {
    if (rows.length < 2) {
        return '';
    }
    const parseRow = (line) =>
        line.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
    const header = parseRow(rows[0]);
    const body = rows.slice(2).map(parseRow);
    const cell = (c) => applyInline(escapeHtml(c));
    const head = `<thead><tr>${header.map((c) => `<th>${cell(c)}</th>`).join('')}</tr></thead>`;
    const tbody = `<tbody>${body
        .map((cells) => `<tr>${cells.map((c) => `<td>${cell(c)}</td>`).join('')}</tr>`)
        .join('')}</tbody>`;
    return `<table class="mk_md_table">${head}${tbody}</table>`;
}

function isTableSeparator(line) {
    return /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/.test(line);
}

export function renderMarkdown(source) {
    if (!source) {
        return '';
    }
    const lines = String(source).split(/\r?\n/);
    const out = [];
    let i = 0;

    const flushParagraph = (buf) => {
        if (!buf.length) return;
        const text = buf.join(' ').trim();
        if (text) {
            out.push(`<p>${applyInline(escapeHtml(text))}</p>`);
        }
        buf.length = 0;
    };

    while (i < lines.length) {
        const line = lines[i];

        // Code fence
        const fence = line.match(/^```(\w+)?\s*$/);
        if (fence) {
            const lang = (fence[1] || '').trim();
            const buf = [];
            i++;
            while (i < lines.length && !/^```\s*$/.test(lines[i])) {
                buf.push(lines[i]);
                i++;
            }
            i++; // skip closing fence
            const code = buf.join('\n');
            const highlighted = highlightCode(code, lang);
            const cls = lang ? ` class="language-${escapeHtml(lang)}"` : '';
            out.push(`<pre class="mk_code"${cls}><code${cls}>${highlighted}</code></pre>`);
            continue;
        }

        // Heading
        const heading = line.match(/^(#{1,4})\s+(.*)$/);
        if (heading) {
            const level = heading[1].length;
            out.push(`<h${level} class="mk_md_h">${applyInline(escapeHtml(heading[2].trim()))}</h${level}>`);
            i++;
            continue;
        }

        // Table (require header + separator rows)
        if (line.startsWith('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
            const rows = [line, lines[i + 1]];
            let j = i + 2;
            while (j < lines.length && lines[j].startsWith('|')) {
                rows.push(lines[j]);
                j++;
            }
            out.push(renderTable(rows));
            i = j;
            continue;
        }

        // Unordered list
        if (/^[-*]\s+/.test(line)) {
            const items = [];
            while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
                items.push(lines[i].replace(/^[-*]\s+/, ''));
                i++;
            }
            out.push(`<ul>${items.map((it) => `<li>${applyInline(escapeHtml(it))}</li>`).join('')}</ul>`);
            continue;
        }

        // Ordered list
        if (/^\d+\.\s+/.test(line)) {
            const items = [];
            while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
                items.push(lines[i].replace(/^\d+\.\s+/, ''));
                i++;
            }
            out.push(`<ol>${items.map((it) => `<li>${applyInline(escapeHtml(it))}</li>`).join('')}</ol>`);
            continue;
        }

        // Paragraph: collect until blank
        const buf = [];
        while (i < lines.length && lines[i].trim() !== '' &&
               !lines[i].startsWith('```') && !/^#{1,4}\s/.test(lines[i]) &&
               !(lines[i].startsWith('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) &&
               !/^[-*]\s+/.test(lines[i]) && !/^\d+\.\s+/.test(lines[i])) {
            buf.push(lines[i]);
            i++;
        }
        flushParagraph(buf);
        while (i < lines.length && lines[i].trim() === '') {
            i++;
        }
    }
    return out.join('\n');
}
