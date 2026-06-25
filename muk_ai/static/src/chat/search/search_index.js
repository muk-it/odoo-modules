function escapeHtml(str) {
    const s = str == null ? '' : String(str);
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Build a searchable index of text entries from rendered conversation turns.
 * @param {Array} renderedTurns rendered turns (user and assistant)
 * @returns {Array} searchable entries with anchor ids
 */
export function buildIndex(renderedTurns) {
    const entries = [];
    const turns = renderedTurns || [];
    for (let turnIndex = 0; turnIndex < turns.length; turnIndex++) {
        const turn = turns[turnIndex];
        if (!turn) continue;
        if (turn.role === 'user') {
            const text = turn.text || '';
            if (text) {
                entries.push({
                    turnIndex,
                    blockIndex: -1,
                    role: 'user',
                    text,
                    anchorId: `mk_msg_${turnIndex}_user`,
                });
            }
        } else if (turn.role === 'assistant') {
            const blocks = turn.blocks || [];
            for (let blockIndex = 0; blockIndex < blocks.length; blockIndex++) {
                const block = blocks[blockIndex];
                if (!block || block.type !== 'text') continue;
                const text = block.text || '';
                if (!text) continue;
                entries.push({
                    turnIndex,
                    blockIndex,
                    role: 'assistant',
                    text,
                    anchorId: `mk_msg_${turnIndex}_${blockIndex}`,
                });
            }
        }
    }
    return entries;
}

/**
 * Find all case-insensitive occurrences of a query across the index.
 * @param {Array} index searchable entries from buildIndex
 * @param {string} query search query
 * @returns {Array} matches with entry and start/end offsets
 */
export function findMatches(index, query) {
    const out = [];
    const q = (query || '').toLowerCase();
    if (!q) return out;
    for (const entry of index || []) {
        const haystack = (entry.text || '').toLowerCase();
        let from = 0;
        while (from <= haystack.length) {
            const at = haystack.indexOf(q, from);
            if (at < 0) break;
            out.push({ entry, start: at, end: at + q.length });
            from = at + Math.max(1, q.length);
        }
    }
    return out;
}

function _wrapTextNode(
    textNode,
    query,
    activeMatchIdx,
    entryFirstMatchIdx,
    counterRef,
) {
    const text = textNode.nodeValue || '';
    const lower = text.toLowerCase();
    const q = query.toLowerCase();
    if (!q || !text) return false;
    const frag = textNode.ownerDocument.createDocumentFragment();
    let from = 0;
    let mutated = false;
    while (from <= lower.length) {
        const at = lower.indexOf(q, from);
        if (at < 0) {
            const tail = text.slice(from);
            if (tail) frag.appendChild(textNode.ownerDocument.createTextNode(tail));
            break;
        }
        if (at > from) {
            frag.appendChild(
                textNode.ownerDocument.createTextNode(text.slice(from, at)),
            );
        }
        const idx = entryFirstMatchIdx + counterRef.local;
        const mark = textNode.ownerDocument.createElement('mark');
        const isActive = idx === activeMatchIdx;
        mark.setAttribute('class', isActive ? 'mk_search_hit_active' : 'mk_search_hit');
        mark.appendChild(
            textNode.ownerDocument.createTextNode(text.slice(at, at + q.length)),
        );
        frag.appendChild(mark);
        counterRef.local += 1;
        mutated = true;
        from = at + Math.max(1, q.length);
    }
    if (mutated) {
        textNode.parentNode.replaceChild(frag, textNode);
    }
    return mutated;
}

function _walk(node, fn) {
    if (!node) return;
    let child = node.firstChild;
    while (child) {
        const next = child.nextSibling;
        if (child.nodeType === 3) {
            fn(child);
        } else if (child.nodeType === 1) {
            const tag = child.tagName ? child.tagName.toLowerCase() : '';
            if (tag === 'script' || tag === 'style' || tag === 'mark') {
                child = next;
                continue;
            }
            _walk(child, fn);
        }
        child = next;
    }
}

/**
 * Wrap query matches in HTML with <mark> tags, marking the active match.
 * @param {string} html source HTML
 * @param {string} query search query
 * @param {number} activeMatchIdx global index of the active match
 * @param {number} entryFirstMatchIdx global index of this entry's first match
 * @returns {string} HTML with highlighted matches
 */
export function highlightHtml(html, query, activeMatchIdx, entryFirstMatchIdx) {
    if (!query) return html;
    if (typeof DOMParser === 'undefined') return html;
    const parser = new DOMParser();
    const doc = parser.parseFromString(
        `<div id="__mk_root__">${html || ''}</div>`,
        'text/html',
    );
    const root = doc.getElementById('__mk_root__');
    if (!root) return html;
    const counter = { local: 0 };
    _walk(root, (textNode) => {
        _wrapTextNode(textNode, query, activeMatchIdx, entryFirstMatchIdx, counter);
    });
    return root.innerHTML;
}

/**
 * HTML-escape plain text and then highlight query matches within it.
 * @param {string} text plain text
 * @param {string} query search query
 * @param {number} activeMatchIdx global index of the active match
 * @param {number} entryFirstMatchIdx global index of this entry's first match
 * @returns {string} escaped HTML with highlighted matches
 */
export function escapeAndHighlight(text, query, activeMatchIdx, entryFirstMatchIdx) {
    const safe = escapeHtml(text || '');
    if (!query) return safe;
    return highlightHtml(safe, query, activeMatchIdx, entryFirstMatchIdx);
}

/**
 * Find the global index of an entry's first match.
 * @param {Array} matches matches from findMatches
 * @param {object} entry the index entry to locate
 * @returns {number} the first match index, or -1 when absent
 */
export function entryFirstMatchIndex(matches, entry) {
    if (!entry) return -1;
    for (let i = 0; i < matches.length; i++) {
        const me = matches[i].entry;
        if (me === entry || (me && me.anchorId === entry.anchorId)) return i;
    }
    return -1;
}
