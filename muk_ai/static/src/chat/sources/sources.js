import { Component, proxy, signal, t, useEffect, useProps, usePlugin } from '@odoo/owl';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';

const DISPLAY_CAP = 8;

/**
 * A source's icon: the site's favicon or the owning app's icon, both served
 * by this Odoo. An absolute URL would make the browser announce itself to
 * another host, so anything not local, or failing to load, falls back to a
 * glyph of the source type.
 */
export class SourceIcon extends Component {
    static template = 'muk_ai.SourceIcon';
    props = useProps({ source: t.object() });
    failed = signal(false);
    get iconUrl() {
        const icon = this.props.source.icon || '';
        return !this.failed() && icon.startsWith('/') && !icon.startsWith('//')
            ? icon
            : '';
    }
}

/** One source as a link: its icon, title and origin. */
export class SourceCard extends Component {
    static template = 'muk_ai.SourceCard';
    static components = { SourceIcon };
    props = useProps({
        source: t.object(),
        sessionId: t.number().optional(),
        focused: t.boolean().optional(false),
    });
    chat = usePlugin(AIChatPlugin);
    root = signal.ref();
    setup() {
        useEffect(() => {
            if (this.props.focused) {
                this.root()?.scrollIntoView({ block: 'nearest' });
            }
        });
    }
    get web() {
        return this.props.source.type === 'web';
    }
    get label() {
        const source = this.props.source;
        return this.web
            ? source.title || source.domain || source.url
            : source.display_name;
    }
    /**
     * Open a cited record beside the chat, docking the chat in a window so the
     * record does not replace it. Citations are lateral, so the breadcrumbs
     * are cleared instead of growing a trail of unrelated records.
     * @param {MouseEvent} ev the click
     */
    async onClick(ev) {
        if (this.web) {
            return;
        }
        ev.preventDefault();
        if (this.props.sessionId) {
            this.chat.openWindow(this.props.sessionId);
        }
        const { res_model, res_id } = this.props.source;
        await this.chat.action.doAction(
            {
                type: 'ir.actions.act_window',
                res_model,
                res_id,
                views: [[false, 'form']],
            },
            { clearBreadcrumbs: true },
        );
    }
}

/** A grid of source cards capped behind a "+N more" toggle. */
export class SourceList extends Component {
    static template = 'muk_ai.SourceList';
    static components = { SourceCard };
    props = useProps({
        sources: t.array(),
        sessionId: t.number().optional(),
        focusItemId: t.any().optional(),
    });
    state = proxy({ showAll: false });
    get visible() {
        const sources = this.props.sources;
        const capped = sources.slice(0, DISPLAY_CAP);
        const focused = this.props.focusItemId;
        const hidden = focused && !capped.some((source) => source.id === focused);
        return this.state.showAll || hidden ? sources : capped;
    }
    get more() {
        return Math.max(0, this.props.sources.length - DISPLAY_CAP);
    }
}
