import { Component, onWillStart, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useDropzone } from '@web/core/dropzone/dropzone_hook';
import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';
import { useService } from '@web/core/utils/hooks';

import { toFileModel } from '@muk_ai/core/attachment/attachment';
import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import {
    approvalPill,
    costTooltip,
    formatCost,
    inputPlaceholder,
    statusBadgeClass,
} from '@muk_ai/chat/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { useAiSession } from '@muk_ai/chat/session/use_ai_session';
import { useChatScrollAnchor } from '@muk_ai/chat/session/use_scroll_anchor';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';
import {
    viewContextLabel,
    viewContextTooltip,
} from '@muk_ai/chat/session/view_context_format';

export class ChatWindow extends Component {
    static template = 'muk_ai.ChatWindow';
    static components = { ChatComposer, ToolCard, AttachmentCard };
    static props = {
        sessionId: { type: Number },
        minimized: { type: Boolean, optional: true },
        onClose: { type: Function },
        onToggleMinimized: { type: Function },
    };
    setup() {
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');
        this.session = useAiSession();
        this.fileViewer = useFileViewer();
        this.rootRef = useRef('root');
        const { scrollRef, scrollToBottom, state: scrollState } = useChatScrollAnchor('scroll');
        this.scrollRef = scrollRef;
        this.scrollToBottom = scrollToBottom;
        this.scrollState = scrollState;
        this.session.setScrollCallback(scrollToBottom);
        this.windowState = useState({ askViews: {} });
        useDropzone(
            this.rootRef,
            (event) => {
                const files = Array.from(event.dataTransfer?.files || []);
                if (files.length) {
                    this.session.onAttachFiles(files);
                }
            },
            'mk_chat_dropzone',
            () => this.session.canAttach() && !this.props.minimized,
        );

        onWillStart(() => this.session.load(this.props.sessionId));
    }
    onOpenAttachment(attachment) {
        const file = toFileModel(attachment);
        this.fileViewer.open(file);
    }
    get renderedTurns() {
        return this.session.renderedTurns();
    }
    renderMarkdown(text) {
        return this.session.renderMarkdown(text);
    }
    isToolExpanded(callId) {
        return this.session.isToolExpanded(callId);
    }
    isToolHiddenForAsk(block, turn) {
        if (block.result !== null && block.result !== undefined) {
            return false;
        }
        const pending = this.session.state.pendingAsk;
        if (pending && pending.call_id === block.callId) {
            return true;
        }
        return turn.blocks.some(
            (b) => b.type === 'ask' && b.callId === block.callId,
        );
    }
    toggleToolBlock(callId) {
        this.session.toggleToolBlock(callId);
    }
    get canSend() {
        return this.session.canSend();
    }
    get canAttach() {
        return this.session.canAttach();
    }
    get canStop() {
        return this.session.canStop();
    }
    get composerDisabled() {
        return this.session.composerDisabled();
    }
    get inputPlaceholder() {
        return inputPlaceholder(this.session.state, _t('Message…'));
    }
    statusBadgeClass(status) {
        return statusBadgeClass(status);
    }
    onInputChange(value) {
        this.session.onInputChange(value);
    }
    onSend() {
        return this.session.onSend();
    }
    onStop() {
        return this.session.onStop();
    }
    onAttachFiles(files) {
        return this.session.onAttachFiles(files);
    }
    onRemoveAttachment(attachmentId) {
        return this.session.onRemoveAttachment(attachmentId);
    }
    async onFullscreen() {
        const sessionId = this.props.sessionId;
        this.chatWindow.close(sessionId);
        await this.action.doAction({
            type: 'ir.actions.client',
            tag: 'muk_ai.chat',
            params: { session_id: sessionId },
        });
    }
    askArgsText(block) {
        return askArgsText(block);
    }
    askViewMode(block) {
        return askViewMode(block, this.windowState.askViews);
    }
    toggleAskView(callId) {
        if (!callId) {
            return;
        }
        const block = this.renderedTurns
            .flatMap((t) => t.blocks || [])
            .find((b) => b.callId === callId);
        this.windowState.askViews = {
            ...this.windowState.askViews,
            [callId]: toggleAskViewMode(block, this.windowState.askViews),
        };
    }
    get viewContextLabel() {
        return viewContextLabel(this.session.state.viewContext);
    }
    get viewContextTooltip() {
        return viewContextTooltip(this.session.state.viewContext);
    }
    get costPill() {
        const cost = this.session.state.totalCost;
        return { label: formatCost(cost), tooltip: costTooltip(cost) };
    }
    get approvalPill() {
        return approvalPill(this.session.state);
    }
}
