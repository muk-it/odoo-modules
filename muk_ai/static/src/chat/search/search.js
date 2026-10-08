import {
    Component,
    onWillDestroy,
    proxy,
    signal,
    t,
    useEffect,
    useProps,
} from '@odoo/owl';

const TEXTS = '.mk_bubble_text, .mk_bubble_body';

/**
 * Find every case-insensitive occurrence of a query in the message texts.
 * @param {HTMLElement} root the transcript
 * @param {string} query the lowercased query
 * @returns {Range[]} the ranges, in document order
 */
function findRanges(root, query) {
    const ranges = [];
    for (const element of root.querySelectorAll(TEXTS)) {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const text = node.nodeValue.toLowerCase();
            for (
                let at = text.indexOf(query);
                at >= 0;
                at = text.indexOf(query, at + query.length)
            ) {
                const range = new Range();
                range.setStart(node, at);
                range.setEnd(node, at + query.length);
                ranges.push(range);
            }
        }
    }
    return ranges;
}

/**
 * Search bar of a transcript. Matches are painted with the CSS Custom
 * Highlight API, so the transcript is never re-rendered to mark them.
 */
export class ChatSearch extends Component {
    static template = 'muk_ai.ChatSearch';
    props = useProps({ target: t.signal(), onClose: t.function() });
    input = signal.ref();
    state = proxy({ query: '', index: 0, total: 0 });
    version = signal(0);
    setup() {
        useEffect(() => this.input()?.focus());
        useEffect(() => {
            const root = this.props.target();
            if (root) {
                const observer = new MutationObserver(() =>
                    this.version.set(this.version() + 1),
                );
                observer.observe(root, {
                    childList: true,
                    subtree: true,
                    characterData: true,
                });
                return () => observer.disconnect();
            }
        });
        useEffect(() => {
            void this.version();
            const root = this.props.target();
            const query = this.state.query.toLowerCase();
            const ranges = root && query ? findRanges(root, query) : [];
            const index = Math.min(this.state.index, ranges.length - 1);
            this.state.total = ranges.length;
            CSS.highlights?.set('mk-search', new Highlight(...ranges));
            CSS.highlights?.set(
                'mk-search-active',
                new Highlight(...ranges.slice(index, index + 1)),
            );
            const key = `${query}:${index}`;
            if (ranges[index] && key !== this.scrolled) {
                this.scrolled = key;
                const hit = ranges[index].startContainer.parentElement;
                hit.scrollIntoView({ block: 'center', behavior: 'smooth' });
                const bubble = hit.closest('.mk_bubble');
                bubble?.classList.add('mk_search_pulse');
                setTimeout(() => bubble?.classList.remove('mk_search_pulse'), 600);
            }
        });
        onWillDestroy(() => {
            CSS.highlights?.delete('mk-search');
            CSS.highlights?.delete('mk-search-active');
        });
    }
    onInput(ev) {
        Object.assign(this.state, { query: ev.target.value, index: 0 });
    }
    move(step) {
        const total = this.state.total;
        if (total) {
            this.state.index = (this.state.index + step + total) % total;
        }
    }
    onKeydown(ev) {
        if (ev.key === 'Escape') {
            this.props.onClose();
        } else if (ev.key === 'Enter') {
            this.move(ev.shiftKey ? -1 : 1);
        } else {
            return;
        }
        ev.preventDefault();
    }
}
