import { Component, proxy, t, useProps, usePlugin } from '@odoo/owl';

import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';
import { _t } from '@web/core/l10n/translation';

import {
    AttachmentCard,
    toFileModel,
    toInlineImageFile,
} from '@muk_ai/core/attachment/attachment';
import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { copyCode, renderMarkdown } from '@muk_ai/core/markdown/markdown';
import {
    buildTurnItems,
    isToolBlockHidden,
    turnRenderers,
} from '@muk_ai/core/session/turns';
import { formatTimestamp } from '@muk_ai/core/utils/utils';
import { SourceIcon, SourceList } from '@muk_ai/chat/sources/sources';
import { ToolCard, ToolGroup } from '@muk_ai/chat/tool_card/tool_card';

/**
 * One turn of a transcript: a user message, a command or compaction marker,
 * an assistant answer with its tools, questions and sources, or a turn an
 * addon draws. Without a session it is shown read only.
 */
export class ChatTurn extends Component {
    static template = 'muk_ai.ChatTurn';
    static components = { AttachmentCard, SourceIcon, SourceList, ToolCard, ToolGroup };
    props = useProps({
        turn: t.object(),
        session: t.object().optional(),
        compact: t.boolean().optional(false),
        hideSources: t.boolean().optional(false),
        onForked: t.function().optional(),
    });
    chat = usePlugin(AIChatPlugin);
    fileViewer = useFileViewer();
    state = proxy({ tools: {}, asks: {}, sources: false });
    renderMarkdown = renderMarkdown;
    formatTimestamp = formatTimestamp;
    get writable() {
        return !!this.props.session && !this.props.session.readonly;
    }
    get pendingAsk() {
        return this.props.session?.data.pending_ask || null;
    }
    get renderer() {
        return turnRenderers.get(this.props.turn.role, null);
    }
    get sourcesLabel() {
        const count = this.props.turn.sources.length;
        return count === 1 ? _t('1 source') : _t('%s sources', count);
    }
    get items() {
        return buildTurnItems(this.props.turn.blocks, (block) => this.isHidden(block));
    }
    isHidden(block) {
        return isToolBlockHidden(block, this.props.turn, this.pendingAsk);
    }
    isStreaming(block) {
        return (
            (block.result === null || block.result === undefined) &&
            !!this.props.session?.busy
        );
    }
    toggleTool(callId) {
        this.state.tools[callId] = !this.state.tools[callId];
    }
    askMode(block) {
        return (
            this.state.asks[block.callId] ||
            (block.preview?.kind ? 'human' : 'technical')
        );
    }
    askToggleTitle(block) {
        return this.askMode(block) === 'technical'
            ? _t('Show friendly view')
            : _t('Show technical view');
    }
    toggleAsk(block) {
        this.state.asks[block.callId] =
            this.askMode(block) === 'human' ? 'technical' : 'human';
    }
    askArgs(block) {
        return JSON.stringify(block.preview?.arguments || block.preview || {}, null, 2);
    }
    /**
     * Branch the chat at an event and let the surface open the branch.
     * @param {number} eventId the last event copied
     */
    async fork(eventId) {
        const id = await this.props.session.forkAtEvent(eventId);
        if (id) {
            this.props.onForked?.(id);
        }
    }
    onClick(ev) {
        const button = ev.target.closest('.mk_code_copy');
        const image = ev.target.closest('.mk_md_image');
        if (button) {
            copyCode(button);
        } else if (image?.src) {
            ev.preventDefault();
            this.fileViewer.open(toInlineImageFile(image.src));
        }
    }
    openAttachment(attachment) {
        this.fileViewer.open(toFileModel(attachment));
    }
}
