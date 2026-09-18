import { Component, onWillStart, useEffect, useState } from '@odoo/owl';

import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';

import { toFileModel } from '@muk_ai/core/attachment/attachment';
import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import { SourceIcon, SourceList } from '@muk_ai/chat/artifacts/types/sources_tab';
import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';
import { isToolBlockHidden, turnRendererFor } from '@muk_ai/chat/session/turns';
import { useAiSession, useSessionState } from '@muk_ai/chat/session/use_ai_session';
import {
    onScrollUpNearTop,
    preserveAnchor,
    useChatScrollAnchor,
} from '@muk_ai/chat/session/use_scroll_anchor';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import { ToolGroup, buildTurnItems } from '@muk_ai/chat/tools/tool_group';
import {
    formatTimestamp,
    statusBadgeClass,
    statusIcon,
    statusLabel,
} from '@muk_ai/chat/utils';

import { closeChild, colorClass } from '@muk_ai_subagents/chat/run/run_store';

/**
 * A subagent's own conversation, in the room the parent's conversation had.
 *
 * A subagent is a session like any other, so opening one navigates to it
 * rather than opening a panel beside the chat: the breadcrumb goes back, and
 * the one composer below writes to whichever of the two is on screen. It runs
 * through a session hook of its own, so its cards act on the subagent.
 */
export class SubagentChildView extends Component {
    static template = 'muk_ai_subagents.SubagentChildView';
    static components = { ToolCard, ToolGroup, AttachmentCard, SourceIcon, SourceList };
    static props = {
        session: { type: Object },
        compact: { type: Boolean, optional: true },
    };
    static defaultProps = { compact: false };
    setup() {
        this.session = useAiSession({ surface: 'window' });
        this.parent = useSessionState(this.props.session);
        this.fileViewer = useFileViewer();
        this.viewState = useState({ askViews: {}, sourcesExpanded: {} });
        const {
            scrollRef,
            scrollToBottom,
            state: scrollState,
        } = useChatScrollAnchor('scroll');
        this.scrollRef = scrollRef;
        this.scrollToBottom = scrollToBottom;
        this.scrollState = scrollState;
        this.session.setScrollCallback(scrollToBottom);
        onScrollUpNearTop(scrollRef, () =>
            preserveAnchor(scrollRef, () => this.session.loadMoreEvents()),
        );
        onWillStart(() => this.session.load(this.open.id));
        useEffect(
            (childId) => {
                if (childId && this.session.state.sessionId !== childId) {
                    this.session.load(childId).then(() => this.scrollToBottom(true));
                }
            },
            () => [this.open ? this.open.id : null],
        );
    }
    get open() {
        return this.parent.state.subagentOpen || { id: null };
    }
    get colorClass() {
        return colorClass(this.open.color);
    }
    get status() {
        return this.session.state.status;
    }
    get parentName() {
        return this.parent.state.name;
    }
    /** The subagent's own name, which is what the user recognises it by. */
    get title() {
        return this.open.agent_name || this.open.name || '';
    }
    /**
     * What this subagent was asked to do, without repeating its name.
     *
     * A subagent is named `<agent>: <objective>` so it can be told apart in a
     * list; in the breadcrumb the name is already the crumb before it.
     * @returns {string} the objective, empty when the name carries none
     */
    get objective() {
        const name = this.open.name || '';
        const prefix = `${this.open.agent_name || ''}: `;
        if (this.open.agent_name && name.startsWith(prefix)) {
            return name.slice(prefix.length);
        }
        return name === this.title ? '' : name;
    }
    get renderedTurns() {
        return this.session.renderedTurns();
    }
    get isCompact() {
        return this.props.compact;
    }
    onBack() {
        closeChild(this.parent);
    }
    onOpenAttachment(attachment) {
        this.fileViewer.open(toFileModel(attachment));
    }
    turnRenderer(turn) {
        return turnRendererFor(turn);
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
    statusBadgeClass(status) {
        return statusBadgeClass(status);
    }
    statusIcon(status) {
        return statusIcon(status);
    }
    statusLabel(status) {
        return statusLabel(status);
    }
    isToolExpanded(callId) {
        return this.session.isToolExpanded(callId);
    }
    isToolHiddenForAsk(block, turn) {
        return isToolBlockHidden(block, turn, this.session.state.pendingAsk);
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
    turnSourcesKey(turn, index) {
        return turn.eventId ? `e${turn.eventId}` : `t${index}`;
    }
    isTurnSourcesExpanded(turn, index) {
        return !!this.viewState.sourcesExpanded[this.turnSourcesKey(turn, index)];
    }
    toggleTurnSources(turn, index) {
        const key = this.turnSourcesKey(turn, index);
        this.viewState.sourcesExpanded = {
            ...this.viewState.sourcesExpanded,
            [key]: !this.viewState.sourcesExpanded[key],
        };
    }
    askArgsText(block) {
        return askArgsText(block);
    }
    askViewMode(block) {
        return askViewMode(block, this.viewState.askViews);
    }
    toggleAskView(callId) {
        if (!callId) {
            return;
        }
        const block = this.renderedTurns
            .flatMap((t) => t.blocks || [])
            .find((b) => b.callId === callId);
        this.viewState.askViews = {
            ...this.viewState.askViews,
            [callId]: toggleAskViewMode(block, this.viewState.askViews),
        };
    }
}
