/** @odoo-module */

import { Component, onMounted, onPatched, onWillStart, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useDropzone } from '@web/core/dropzone/dropzone_hook';
import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';
import { useService } from '@web/core/utils/hooks';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

import { toFileModel } from '@muk_ai/core/attachment/attachment';
import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { useAiSession } from '@muk_ai/chat/session/use_ai_session';
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

const SCROLL_NEAR_BOTTOM = 160;

export class ChatWindow extends Component {
    static template = 'muk_ai.ChatWindow';
    static components = { ChatComposer, ToolCard, AttachmentCard, Dropdown, DropdownItem };
    static props = {
        sessionId: { type: Number },
        minimized: { type: Boolean, optional: true },
        onClose: { type: Function },
        onToggleMinimized: { type: Function },
    };

    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');
        this.session = useAiSession();
        this.fileViewer = useFileViewer();
        this.rootRef = useRef('root');
        this.scrollRef = useRef('scroll');
        this.session.setScrollCallback(() => this._scrollToBottom());
        this._shouldAutoScroll = true;
        this.windowState = useState({ agents: [], askViews: {} });
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

        onWillStart(async () => {
            await Promise.all([this.session.load(this.props.sessionId), this._loadAgents()]);
        });
        onMounted(() => this._scrollToBottom(true));
        onPatched(() => this._shouldAutoScroll && this._scrollToBottom());
    }

    async _loadAgents() {
        this.windowState.agents = await this.orm.searchRead(
            'muk_ai.agent',
            [['active', '=', true]],
            ['id', 'name', 'description'],
            { order: 'sequence, name' },
        );
    }

    async onSetAgent(agentId) {
        const agent = this.windowState.agents.find((a) => a.id === agentId);
        await this.session.setAgent(agentId || null, agent ? agent.name : '');
    }

    onOpenAttachment(attachment) {
        const file = toFileModel(attachment);
        this.fileViewer.open(file);
    }

    _scrollToBottom(force) {
        const el = this.scrollRef.el;
        if (!el) {
            return;
        }
        if (!force) {
            const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
            if (distance > SCROLL_NEAR_BOTTOM) {
                this._shouldAutoScroll = false;
                return;
            }
        }
        this._shouldAutoScroll = true;
        requestAnimationFrame(() => {
            el.scrollTop = el.scrollHeight;
        });
    }

    // ----------------------------------------------------------
    // Template helpers
    // ----------------------------------------------------------

    get renderedTurns() {
        return this.session.renderedTurns();
    }

    renderMarkdown(text) {
        return this.session.renderMarkdown(text);
    }

    isToolExpanded(callId) {
        return this.session.isToolExpanded(callId);
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
        if (this.session.state.status === 'waiting') {
            const kind = (this.session.state.pendingAsk || {}).kind;
            return kind === 'approval'
                ? _t('Approve or reject to continue…')
                : _t('Type your answer…');
        }
        if (this.session.state.status === 'running') {
            return _t('Stop to interrupt…');
        }
        return _t('Message…');
    }

    statusBadgeClass(status) {
        return {
            new: 'mk_state_new',
            running: 'mk_state_running',
            waiting: 'mk_state_waiting',
            done: 'mk_state_done',
            error: 'mk_state_error',
            stopped: 'mk_state_stopped',
        }[status] || 'mk_state_new';
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

    get costLabel() {
        const cost = Number(this.session.state.totalCost) || 0;
        if (!cost) {
            return '0';
        }
        if (cost < 0.01) {
            return cost.toFixed(4);
        }
        if (cost < 1) {
            return cost.toFixed(3);
        }
        return cost.toFixed(2);
    }

    get costTooltip() {
        const cost = Number(this.session.state.totalCost) || 0;
        return `Session cost so far: $${cost.toFixed(6)} (USD)`;
    }

    get viewContextTooltip() {
        return viewContextTooltip(this.session.state.viewContext);
    }

    get approvalPillLabel() {
        const mode = this.session.state.effectiveApprovalMode || 'ask';
        return mode === 'off' ? _t("YOLO") : _t("Ask");
    }

    get approvalPillClass() {
        const mode = this.session.state.effectiveApprovalMode || 'ask';
        const base = mode === 'off' ? 'mk_approval_yolo' : 'mk_approval_ask';
        const isOverride = this.session.state.approvalMode !== false
            && this.session.state.approvalMode !== undefined;
        return `${base}${isOverride ? ' mk_approval_override' : ''}`;
    }

    get approvalPillIcon() {
        const mode = this.session.state.effectiveApprovalMode || 'ask';
        return mode === 'off' ? 'fa-bolt' : 'fa-shield';
    }

    get approvalPillTooltip() {
        const mode = this.session.state.effectiveApprovalMode || 'ask';
        const override = this.session.state.approvalMode !== false
            && this.session.state.approvalMode !== undefined;
        if (mode === 'off') {
            return override
                ? _t("YOLO (override). Click to cycle.")
                : _t("YOLO (from agent). Click to cycle.");
        }
        return override
            ? _t("Ask before risky writes (override). Click to cycle.")
            : _t("Ask before risky writes (from agent). Click to cycle.");
    }
}
