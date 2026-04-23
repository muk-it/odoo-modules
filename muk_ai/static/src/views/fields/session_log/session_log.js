/** @odoo-module */

import { Component, markup, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import { renderMarkdown as renderMarkdownToHtml } from '@muk_ai/core/markdown/markdown';
import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';

export class SessionLogField extends Component {
    static template = 'muk_ai.SessionLogField';
    static components = { AttachmentCard, ToolCard };
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            expandedTools: {},
            askViews: {},
        });
        this.session = { state: { pendingAsk: null } };
    }

    get turns() {
        const value = this.props.record.data[this.props.name];
        if (!Array.isArray(value) || !value.length) {
            return [];
        }
        return buildRenderedTurns(value);
    }

    renderMarkdown(source) {
        return markup(renderMarkdownToHtml(source));
    }

    isToolExpanded(callId) {
        return !!this.state.expandedTools[callId];
    }

    toggleToolBlock(callId) {
        this.state.expandedTools[callId] = !this.state.expandedTools[callId];
    }

    askViewMode(block) {
        return askViewMode(block, this.state.askViews);
    }

    toggleAskView(callId) {
        const block = { callId };
        this.state.askViews[callId] = toggleAskViewMode(
            block,
            this.state.askViews,
        );
    }

    askArgsText(block) {
        return askArgsText(block);
    }

    onOpenAttachment() {}
}

export const sessionLogField = {
    component: SessionLogField,
    displayName: _t('AI Session Log'),
    supportedTypes: ['json'],
};

registry.category('fields').add('ai_session_log', sessionLogField);
