import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { user } from '@web/core/user';
import { useService } from '@web/core/utils/hooks';
import { useDropzone } from '@web/core/dropzone/dropzone_hook';
import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';

import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

import { toFileModel, toInlineImageFile } from '@muk_ai/core/attachment/attachment';
import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import {
    approvalPill,
    costTooltip,
    formatCost,
    inputPlaceholder,
    statusLabel,
} from '@muk_ai/chat/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { useAiSession } from '@muk_ai/chat/session/use_ai_session';
import { useChatScrollAnchor } from '@muk_ai/chat/session/use_scroll_anchor';
import { ChatSidebar } from '@muk_ai/chat/sidebar/chat_sidebar';
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

const SESSION_LIST_LIMIT = 50;

function normalizeSuggestions(raw) {
    if (!Array.isArray(raw)) {
        return [];
    }
    return raw
        .filter((s) => s && typeof s.prompt === 'string' && s.prompt.trim())
        .map((s) => ({
            label: (typeof s.label === 'string' && s.label) || s.prompt,
            prompt: s.prompt,
        }));
}

export class AIChat extends Component {
    static template = 'muk_ai.Chat';
    static components = { ChatSidebar, ToolCard, ChatComposer, AttachmentCard, Dropdown, DropdownItem };
    static props = ['*'];
    get suggestions() {
        const agents = this.session.state.agents || [];
        const agent = agents.find((a) => a.id === this.session.state.agentId)
            || agents[0];
        return normalizeSuggestions(agent && agent.suggestions);
    }
    setup() {
        this.orm = useService('orm');
        this.bus = useService('bus_service');
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');

        this.session = useAiSession({
            onRefresh: () => this._loadSessions(),
        });
        this.fileViewer = useFileViewer();
        this.state = useState({
            loading: true,
            sessions: [],
            sidebarHidden: false,
            askViews: {},
        });
        this.rootRef = useRef('root');
        const { scrollRef, scrollToBottom, state: scrollState } = useChatScrollAnchor('scrollArea');
        this.scrollRef = scrollRef;
        this.scrollToBottom = scrollToBottom;
        this.scrollState = scrollState;
        this.session.setScrollCallback(scrollToBottom);
        this._userBusHandler = null;
        this._loadSeq = 0;
        useDropzone(
            this.rootRef,
            (event) => {
                const files = Array.from(event.dataTransfer?.files || []);
                if (files.length) {
                    this.session.onAttachFiles(files);
                }
            },
            'mk_chat_dropzone',
            () => this.session.canAttach(),
        );

        onWillStart(async () => {
            await Promise.all([this._loadSessions(), this.session.loadAgents()]);
            this._connectUserBus();
            const requested = this._getRequestedSessionId();
            const isMobile = typeof window !== 'undefined'
                && window.innerWidth < 768;
            if (requested && this.state.sessions.some((s) => s.id === requested)) {
                await this._selectSession(requested);
                this.state.sidebarHidden = true;
            } else if (this.state.sessions.length) {
                await this._selectSession(this.state.sessions[0].id);
                if (isMobile) {
                    this.state.sidebarHidden = true;
                }
            }
            this.state.loading = false;
        });

        onMounted(() => this._installImageClickHandler());
        onWillUnmount(() => this._disconnectUserBus());
    }
    _installImageClickHandler() {
        const root = this.rootRef.el;
        if (!root) return;
        root.addEventListener('click', (ev) => {
            const img = ev.target.closest('.mk_md_image');
            if (!img || !img.src) return;
            ev.preventDefault();
            this._openInlineImage(img.src);
        });
    }
    _openInlineImage(src) {
        this.fileViewer.open(toInlineImageFile(src));
    }
    async _loadSessions() {
        const seq = ++this._loadSeq;
        const sessions = await this.orm.searchRead(
            'muk_ai.session',
            [['user_id', '=', user.userId]],
            ['id', 'name', 'state', 'create_date'],
            { limit: SESSION_LIST_LIMIT, order: 'create_date DESC' },
        );
        if (seq === this._loadSeq) {
            this.state.sessions = sessions;
        }
    }
    async _selectSession(sessionId) {
        if (this.session.state.sessionId === sessionId) {
            return;
        }
        await this.session.load(sessionId);
        this.scrollToBottom(true);
        if (typeof window !== 'undefined' && window.innerWidth < 768) {
            this.state.sidebarHidden = true;
        }
    }
    async onNewSession() {
        const name = _t('Chat %s', new Date().toLocaleString());
        const sessionId = await this.orm.create('muk_ai.session', [{ name }]);
        const id = Array.isArray(sessionId) ? sessionId[0] : sessionId;
        await this._loadSessions();
        await this._selectSession(id);
    }
    async onStartWithPrompt(prompt) {
        await this.onNewSession();
        this.session.state.input = prompt;
        this.session.state.focusToken += 1;
        await this.session.onSend();
        this._refreshSidebar();
    }
    async onSubmitSuggestion(prompt) {
        this.session.state.input = prompt;
        this.session.state.focusToken += 1;
        await this.session.onSend();
        this._refreshSidebar();
    }
    async onSelectSession(sessionId) {
        await this._selectSession(sessionId);
    }
    async onRenameSession(sessionId, name) {
        await this.orm.write('muk_ai.session', [sessionId], { name });
        await this._loadSessions();
        if (this.session.state.sessionId === sessionId) {
            this.session.state.name = name;
        }
    }
    async onDeleteSession(sessionId) {
        await this.orm.unlink('muk_ai.session', [sessionId]);
        await this._loadSessions();
        if (this.session.state.sessionId === sessionId) {
            const next = this.state.sessions[0]?.id || null;
            await this._selectSession(next);
        }
    }
    toggleSidebar() {
        this.state.sidebarHidden = !this.state.sidebarHidden;
    }
    onPopout() {
        if (!this.session.state.sessionId) {
            return;
        }
        this.chatWindow.open(this.session.state.sessionId);
    }
    async onSend() {
        await this.session.onSend();
        this._refreshSidebar();
    }
    async onStop() {
        await this.session.onStop();
        this._refreshSidebar();
    }
    onInputChange(value) {
        this.session.onInputChange(value);
    }
    onAttachFiles(files) {
        return this.session.onAttachFiles(files);
    }
    onRemoveAttachment(attachmentId) {
        return this.session.onRemoveAttachment(attachmentId);
    }
    toggleToolBlock(callId) {
        this.session.toggleToolBlock(callId);
    }
    onOpenAttachment(attachment) {
        const file = toFileModel(attachment);
        this.fileViewer.open(file);
    }
    _connectUserBus() {
        this._disconnectUserBus();
        this._userBusHandler = (payload) => this._onUserBusEvent(payload);
        this.bus.subscribe('muk_ai.session_state', this._userBusHandler);
    }
    _disconnectUserBus() {
        if (this._userBusHandler) {
            this.bus.unsubscribe('muk_ai.session_state', this._userBusHandler);
            this._userBusHandler = null;
        }
    }
    _onUserBusEvent(payload) {
        if (!payload || !payload.session_id) {
            return;
        }
        const idx = this.state.sessions.findIndex((s) => s.id === payload.session_id);
        if (idx < 0) {
            this._loadSessions();
            return;
        }
        const updated = { ...this.state.sessions[idx] };
        if (payload.state) updated.state = payload.state;
        if (payload.name) updated.name = payload.name;
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
        if (payload.session_id === this.session.state.sessionId) {
            if (payload.state) this.session.state.status = payload.state;
            if (typeof payload.iteration_count === 'number') {
                this.session.state.iterationCount = payload.iteration_count;
            }
            if (typeof payload.total_input_tokens === 'number') {
                this.session.state.inputTokens = payload.total_input_tokens;
            }
            if (typeof payload.total_output_tokens === 'number') {
                this.session.state.outputTokens = payload.total_output_tokens;
            }
            if (typeof payload.last_input_tokens === 'number') {
                this.session.state.lastInputTokens = payload.last_input_tokens;
            }
            if (typeof payload.context_window === 'number') {
                this.session.state.contextWindow = payload.context_window;
            }
        }
    }
    _refreshSidebar() {
        const id = this.session.state.sessionId;
        if (!id) return;
        const idx = this.state.sessions.findIndex((s) => s.id === id);
        if (idx < 0) {
            this._loadSessions();
            return;
        }
        const updated = {
            ...this.state.sessions[idx],
            state: this.session.state.status,
        };
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
    }
    _getRequestedSessionId() {
        try {
            const actionParam = this.props?.action?.params?.session_id;
            if (actionParam) {
                const actionId = parseInt(actionParam, 10);
                if (Number.isInteger(actionId) && actionId > 0) {
                    return actionId;
                }
            }
            const params = new URLSearchParams(window.location.search);
            const raw = params.get('session_id');
            const id = raw ? parseInt(raw, 10) : 0;
            return Number.isInteger(id) && id > 0 ? id : null;
        } catch (_e) {
            return null;
        }
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
        return inputPlaceholder(
            this.session.state,
            _t('Message the assistant… (Enter to send, Shift+Enter for newline)'),
        );
    }
    statusLabel(status) {
        return statusLabel(status);
    }
    get contextPercent() {
        const window = this.session.state.contextWindow;
        if (!window) {
            return 0;
        }
        return Math.max(
            0,
            Math.min(100, Math.round(
                (this.session.state.lastInputTokens / window) * 100,
            )),
        );
    }
    get contextClass() {
        const pct = this.contextPercent;
        if (pct >= 90) return 'mk_context_red';
        if (pct >= 70) return 'mk_context_amber';
        return 'mk_context_green';
    }
    get contextIcon() {
        const pct = this.contextPercent;
        if (pct >= 90) return 'fa-battery-empty';
        if (pct >= 70) return 'fa-battery-quarter';
        if (pct >= 40) return 'fa-battery-half';
        if (pct > 0) return 'fa-battery-three-quarters';
        return 'fa-battery-full';
    }
    get costPill() {
        const cost = this.session.state.totalCost;
        return { label: formatCost(cost), tooltip: costTooltip(cost) };
    }
    get contextTooltip() {
        const tokens = this.session.state.lastInputTokens || 0;
        const window = this.session.state.contextWindow || 0;
        const fmt = new Intl.NumberFormat();
        return _t(
            'Context window: %(tokens)s / %(window)s tokens',
            { tokens: fmt.format(tokens), window: fmt.format(window) },
        );
    }
    askArgsText(block) {
        return askArgsText(block);
    }
    askViewMode(block) {
        return askViewMode(block, this.state.askViews);
    }
    toggleAskView(callId) {
        if (!callId) {
            return;
        }
        const block = this.renderedTurns
            .flatMap((t) => t.blocks || [])
            .find((b) => b.callId === callId);
        this.state.askViews = {
            ...this.state.askViews,
            [callId]: toggleAskViewMode(block, this.state.askViews),
        };
    }
    get viewContextLabel() {
        return viewContextLabel(this.session.state.viewContext);
    }
    get viewContextTooltip() {
        return viewContextTooltip(this.session.state.viewContext);
    }
    get approvalPill() {
        return approvalPill(this.session.state);
    }
}

registry.category('actions').add('muk_ai.chat', AIChat);
