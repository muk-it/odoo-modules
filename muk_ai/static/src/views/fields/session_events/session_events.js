import { Component, markup, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import { ToolGroup, buildTurnItems } from '@muk_ai/chat/tools/tool_group';
import { renderMarkdown as renderMarkdownToHtml } from '@muk_ai/core/markdown/markdown';
import { buildRenderedTurns } from '@muk_ai/chat/session/turns';
import { formatTimestamp } from '@muk_ai/chat/utils';
import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';

/** Read-only field rendering a session's events as a chat-style transcript. */
export class SessionEventsField extends Component {
    static template = 'muk_ai.SessionEventsField';
    static components = { AttachmentCard, ToolCard, ToolGroup };
    static props = { ...standardFieldProps };
    setup() {
        this.notification = useService('notification');
        this.state = useState({
            expandedTools: {},
            askViews: {},
        });
        this.session = {
            state: { pendingAsk: null },
            copyText: (text) => this.copyText(text),
        };
    }
    get turns() {
        const value = this.props.record.data[this.props.name];
        if (!Array.isArray(value) || !value.length) {
            return [];
        }
        return buildRenderedTurns(value);
    }
    turnItems(turn) {
        return buildTurnItems(turn.blocks, (block) =>
            this.isToolHiddenForAsk(block, turn),
        );
    }
    get isCompact() {
        return true;
    }
    get hideSources() {
        return true;
    }
    renderMarkdown(source) {
        return markup(renderMarkdownToHtml(source));
    }
    renderUserText(text) {
        return text == null ? '' : String(text);
    }
    renderAssistantMarkdown(text) {
        return this.renderMarkdown(text);
    }
    isToolExpanded(callId) {
        return !!this.state.expandedTools[callId];
    }
    isToolHiddenForAsk(block, turn) {
        if (block.result !== null && block.result !== undefined) {
            return false;
        }
        return turn.blocks.some((b) => b.type === 'ask' && b.callId === block.callId);
    }
    isToolStreaming() {
        return false;
    }
    toggleToolBlock(callId) {
        this.state.expandedTools = {
            ...this.state.expandedTools,
            [callId]: !this.state.expandedTools[callId],
        };
    }
    askViewMode(block) {
        return askViewMode(block, this.state.askViews);
    }
    toggleAskView(callId) {
        if (!callId) {
            return;
        }
        const block = this.turns
            .flatMap((turn) => turn.blocks || [])
            .find((b) => b.callId === callId);
        this.state.askViews[callId] = toggleAskViewMode(block, this.state.askViews);
    }
    askArgsText(block) {
        return askArgsText(block);
    }
    formatTimestamp(at) {
        return formatTimestamp(at);
    }
    copyText(text) {
        if (!text || !navigator.clipboard) {
            return;
        }
        navigator.clipboard.writeText(String(text)).then(
            () => this.notification.add(_t('Copied to clipboard'), { type: 'success' }),
            () => this.notification.add(_t('Copy failed'), { type: 'danger' }),
        );
    }
    onOpenAttachment() {}
}

export const sessionEventsField = {
    component: SessionEventsField,
    displayName: _t('AI Session Events'),
    supportedTypes: ['json'],
};

registry.category('fields').add('ai_session_events', sessionEventsField);
