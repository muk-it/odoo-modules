import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useDropzone } from '@web/core/dropzone/dropzone_hook';
import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';
import { useService } from '@web/core/utils/hooks';

import { toFileModel } from '@muk_ai/core/attachment/attachment';
import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import { SourceIcon, SourceList } from '@muk_ai/chat/artifacts/types/sources_tab';
import {
    approvalPill,
    costTooltip,
    formatCost,
    formatRelativeTime,
    formatTimestamp,
    inputPlaceholder,
    statusBadgeClass,
    statusIcon,
    statusLabel,
} from '@muk_ai/chat/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { useAiSession } from '@muk_ai/chat/session/use_ai_session';
import {
    onScrollUpNearTop,
    preserveAnchor,
    useChatScrollAnchor,
} from '@muk_ai/chat/session/use_scroll_anchor';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import { ToolGroup, buildTurnItems } from '@muk_ai/chat/tools/tool_group';
import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';
import {
    viewContextLabel,
    viewContextTooltip,
} from '@muk_ai/chat/session/view_context_format';

/** Floating chat window hosting one AI session with composer and turns. */
export class ChatWindow extends Component {
    static template = 'muk_ai.ChatWindow';
    static components = {
        ChatComposer,
        ToolCard,
        ToolGroup,
        AttachmentCard,
        SourceIcon,
        SourceList,
    };
    static props = {
        sessionId: { type: Number },
        minimized: { type: Boolean, optional: true },
        onClose: { type: Function },
        onToggleMinimized: { type: Function },
    };
    setup() {
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');
        this.session = useAiSession({
            surface: 'window',
            onForked: (newId) => {
                this.chatWindow.open(newId);
            },
            onHandedOver: () => this.props.onClose(),
        });
        this.fileViewer = useFileViewer();
        this.rootRef = useRef('root');
        const {
            scrollRef,
            scrollToBottom,
            state: scrollState,
        } = useChatScrollAnchor('scroll');
        this.scrollRef = scrollRef;
        this.scrollToBottom = scrollToBottom;
        this.scrollState = scrollState;
        this.session.setScrollCallback(scrollToBottom);
        this.windowState = useState({
            askViews: {},
            resumeTick: 0,
            sourcesExpanded: {},
        });
        this._resumeTickInterval = null;
        onScrollUpNearTop(scrollRef, () =>
            preserveAnchor(scrollRef, () => this.session.loadMoreEvents()),
        );
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
        useEffect(
            (minimized) => {
                if (!minimized) {
                    this.scrollToBottom(true);
                }
            },
            () => [this.props.minimized],
        );
        onWillStart(() =>
            Promise.all([
                this.session.load(this.props.sessionId),
                this.session.loadAgents(),
            ]),
        );
        onMounted(() => {
            this._installRootPasteHandler();
            this._resumeTickInterval = window.setInterval(() => {
                if (
                    this.session.state.status === 'waiting_schedule' &&
                    this.session.state.resumeAt
                ) {
                    this.windowState.resumeTick += 1;
                }
            }, 5000);
        });
        onWillUnmount(() => {
            this._uninstallRootPasteHandler();
            if (this._resumeTickInterval !== null) {
                window.clearInterval(this._resumeTickInterval);
                this._resumeTickInterval = null;
            }
        });
    }
    _installRootPasteHandler() {
        const root = this.rootRef.el;
        if (!root) return;
        this._rootPasteHandler = (ev) => {
            if (!root.isConnected) return;
            if (!this.session.canAttach() || this.props.minimized) return;
            if (ev.target && ev.target.closest('.mk_composer textarea')) return;
            const items = (ev.clipboardData && ev.clipboardData.items) || [];
            const files = [];
            for (const item of items) {
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file) files.push(file);
                }
            }
            if (files.length) {
                ev.preventDefault();
                this.session.onAttachFiles(files);
            }
        };
        document.addEventListener('paste', this._rootPasteHandler);
    }
    _uninstallRootPasteHandler() {
        if (this._rootPasteHandler) {
            document.removeEventListener('paste', this._rootPasteHandler);
        }
        this._rootPasteHandler = null;
    }
    onOpenAttachment(attachment) {
        const file = toFileModel(attachment);
        this.fileViewer.open(file);
    }
    turnSourcesKey(turn, index) {
        return turn.eventId ? `e${turn.eventId}` : `t${index}`;
    }
    isTurnSourcesExpanded(turn, index) {
        return !!this.windowState.sourcesExpanded[this.turnSourcesKey(turn, index)];
    }
    toggleTurnSources(turn, index) {
        const key = this.turnSourcesKey(turn, index);
        this.windowState.sourcesExpanded = {
            ...this.windowState.sourcesExpanded,
            [key]: !this.windowState.sourcesExpanded[key],
        };
    }
    get renderedTurns() {
        return this.session.renderedTurns();
    }
    renderMarkdown(text) {
        return this.session.renderMarkdown(text);
    }
    renderUserText(text) {
        return text == null ? '' : String(text);
    }
    renderAssistantMarkdown(text) {
        return this.session.renderMarkdown(text);
    }
    formatTimestamp(at) {
        return formatTimestamp(at);
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
        return turn.blocks.some((b) => b.type === 'ask' && b.callId === block.callId);
    }
    isToolStreaming(block) {
        if (block.result !== null && block.result !== undefined) {
            return false;
        }
        const status = this.session.state.status;
        return status === 'running' || status === 'compacting';
    }
    toggleToolBlock(callId) {
        this.session.toggleToolBlock(callId);
    }
    turnItems(turn) {
        return buildTurnItems(turn.blocks, (block) =>
            this.isToolHiddenForAsk(block, turn),
        );
    }
    get isCompact() {
        return true;
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
    get isQueueing() {
        return this.session.isQueueing();
    }
    get inputPlaceholder() {
        return inputPlaceholder(this.session.state, _t('Message…'));
    }
    statusBadgeClass(status) {
        return statusBadgeClass(status);
    }
    statusIcon(status) {
        return statusIcon(status);
    }
    statusLabel(status) {
        return statusLabel(status);
    }
    get resumeRelativeText() {
        void this.windowState.resumeTick;
        const relative = formatRelativeTime(this.session.state.resumeAt);
        if (!relative) {
            return '';
        }
        return _t('resumes in %s', relative);
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
