import { Component, useState } from '@odoo/owl';

import { useService } from '@web/core/utils/hooks';

/**
 * A source's icon: the site's favicon for a web page, the owning app's icon
 * for a record. Both are resolved server-side and arrive on the descriptor;
 * anything the server could not resolve, or that fails to load, falls back to
 * the type's glyph.
 */
export class SourceIcon extends Component {
    static template = 'muk_ai.SourceIcon';
    static props = {
        source: { type: Object },
    };
    setup() {
        this.state = useState({ iconFailed: false });
    }
    get iconUrl() {
        return this.state.iconFailed ? '' : this.props.source.icon || '';
    }
    onIconError() {
        this.state.iconFailed = true;
    }
}

/** A single source row: a favicon/icon, a title, and its origin, as a link. */
export class SourceCard extends Component {
    static template = 'muk_ai.SourceCard';
    static components = { SourceIcon };
    static props = {
        source: { type: Object },
        sessionId: { type: [Number, String], optional: true },
    };
    setup() {
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');
    }
    /**
     * Open a cited record beside the chat, docking the conversation first so
     * the record does not replace it. Web sources fall through to the anchor.
     * Breadcrumbs are cleared because citations are lateral, not a drill-down:
     * stacking them would grow an unbounded trail of unrelated records.
     * @param {MouseEvent} ev click on the card
     * @returns {Promise<void>}
     */
    async onSourceClick(ev) {
        if (this.props.source.type !== 'record') {
            return;
        }
        ev.preventDefault();
        if (this.props.sessionId) {
            this.chatWindow.open(this.props.sessionId);
        }
        await this.action.doAction(
            {
                type: 'ir.actions.act_window',
                res_model: this.props.source.res_model,
                res_id: this.props.source.res_id,
                views: [[false, 'form']],
                target: 'current',
            },
            { clearBreadcrumbs: true },
        );
    }
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
        sessionId: { type: [Number, String], optional: true },
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
