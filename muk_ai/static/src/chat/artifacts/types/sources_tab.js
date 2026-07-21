import { Component, useState } from '@odoo/owl';

/** A source's favicon (web) or type glyph, in a small circle, with a fallback. */
export class SourceIcon extends Component {
    static template = 'muk_ai.SourceIcon';
    static props = {
        source: { type: Object },
    };
    setup() {
        this.state = useState({ faviconFailed: false });
    }
    get faviconUrl() {
        const source = this.props.source;
        if (source.type !== 'web' || this.state.faviconFailed || !source.domain) {
            return '';
        }
        return `https://${source.domain}/favicon.ico`;
    }
    onFaviconError() {
        this.state.faviconFailed = true;
    }
}

/** A single source row: a favicon/icon, a title, and its origin, as a link. */
export class SourceCard extends Component {
    static template = 'muk_ai.SourceCard';
    static components = { SourceIcon };
    static props = {
        source: { type: Object },
    };
    get href() {
        const source = this.props.source;
        return source.type === 'web' ? source.url : source.href || '#';
    }
    get label() {
        const source = this.props.source;
        return source.type === 'web'
            ? source.title || source.domain || source.url
            : source.display_name;
    }
    get origin() {
        const source = this.props.source;
        return source.type === 'web' ? source.domain : source.res_model;
    }
}

const SOURCE_LIST_DISPLAY_CAP = 8;

/** A capped grid of source cards with a "+N more" toggle to reveal the rest. */
export class SourceList extends Component {
    static template = 'muk_ai.SourceList';
    static components = { SourceCard };
    static props = {
        sources: { type: Array },
        cap: { type: Number, optional: true },
    };
    setup() {
        this.state = useState({ showAll: false });
    }
    get cap() {
        return this.props.cap || SOURCE_LIST_DISPLAY_CAP;
    }
    get visible() {
        return this.state.showAll
            ? this.props.sources
            : this.props.sources.slice(0, this.cap);
    }
    get hiddenCount() {
        return Math.max(0, this.props.sources.length - this.cap);
    }
    toggle() {
        this.state.showAll = !this.state.showAll;
    }
}

/** Artifacts tab listing the session's cited sources (web pages, records). */
export class SourcesTab extends Component {
    static template = 'muk_ai.SourcesTab';
    static components = { SourceList };
    static props = {
        items: { type: Array },
        session: { type: Object, optional: true },
        onOpenAttachment: { type: Function, optional: true },
    };
}
