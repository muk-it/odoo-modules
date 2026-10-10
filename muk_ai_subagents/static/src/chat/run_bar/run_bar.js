// @odoo-module

import { Component } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { AIChat } from '@muk_ai/chat/chat';
import { useSessionState } from '@muk_ai/chat/session/use_ai_session';
import { ChatWindow } from '@muk_ai/chat/window/chat_window';

import { childStatus, openChat } from '@muk_ai_subagents/chat/run/run';
import { SubagentRunCard } from '@muk_ai_subagents/chat/run_card/run_card';

/**
 * What sits above the composer for a delegation: the subagents of the run while
 * any of them works, and in a subagent's own chat the chat it works for.
 */
export class SubagentBar extends Component {
    static template = 'muk_ai_subagents.SubagentBar';
    static components = { SubagentRunCard };
    static props = { session: { type: Object } };
    setup() {
        this.session = useSessionState(this.props.session);
        this.services = {
            action: useService('action'),
            ui: useService('ui'),
            chatWindow: useService('muk_ai.chat_window'),
        };
    }
    get parent() {
        return this.session.state.subagent_of || null;
    }
    /**
     * The run to dock while any of its subagents works.
     * @returns {object|null} a run card turn, null when nothing is docked
     */
    get docked() {
        const children = this.session.state.subagents?.children || [];
        const live = children.some((child) =>
            ['working', 'needs_you'].includes(childStatus(child)),
        );
        return live ? { callId: false, children } : null;
    }
    get steerHint() {
        return this.session.isQueueing()
            ? _t('Messages reach %s after its current step', this.parent.agent_name)
            : '';
    }
    openParent() {
        openChat(this.services, this.parent.parent_id);
    }
}

AIChat.components = { ...AIChat.components, SubagentBar };
ChatWindow.components = { ...ChatWindow.components, SubagentBar };
