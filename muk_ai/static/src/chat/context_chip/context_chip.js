import { Component, t, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import { modelNames } from '@muk_ai/chat/tool_card/tool_labels';

/** The view a chat is pinned to, opening it on click and unpinning it. */
export class ContextChip extends Component {
    static template = 'muk_ai.ContextChip';
    props = useProps({ session: t.object() });
    get label() {
        const context = this.props.session.data.view_context;
        const model = modelNames(context.model).name;
        if (context.kind === 'record') {
            const name = context.display_name || (context.id ? `#${context.id}` : '');
            return name ? `${model} · ${name}` : model;
        }
        if (context.kind === 'list') {
            return `${model} · ${context.view_type || 'list'}`;
        }
        return model || _t('Action');
    }
    get tooltip() {
        const context = this.props.session.data.view_context;
        const domain =
            context.kind === 'list' && context.domain?.length
                ? JSON.stringify(context.domain)
                : '';
        return [this.label, domain, _t('Click to open · /unpin to clear')]
            .filter(Boolean)
            .join('\n');
    }
}
