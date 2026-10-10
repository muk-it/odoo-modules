import { Component, t, useProps, usePlugin } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { UIPlugin } from '@web/core/ui/ui_plugin';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { composerAccessories } from '@muk_ai/chat/conversation/conversation';

import { childStatus, openChat } from '@muk_ai_subagents/chat/run/run';
import { SubagentRunCard } from '@muk_ai_subagents/chat/run_card/run_card';

/**
 * What sits above the composer for a delegation: the subagents of the run while
 * any of them works, and in a subagent's own chat the chat it works for.
 */
export class SubagentBar extends Component {
    static template = 'muk_ai_subagents.SubagentBar';
    static components = { SubagentRunCard };
    props = useProps({ session: t.object() });
    chat = usePlugin(AIChatPlugin);
    ui = usePlugin(UIPlugin);
    get parent() {
        return this.props.session.data.subagent_of || null;
    }
    /**
     * The run to dock while any of its subagents works.
     * @returns {object|null} a run card turn, null when nothing is docked
     */
    get docked() {
        const children = this.props.session.data.subagents?.children || [];
        const live = children.some((child) =>
            ['working', 'needs_you'].includes(childStatus(child)),
        );
        return live ? { callId: false, children } : null;
    }
    get steerHint() {
        return this.props.session.queueing
            ? _t('Messages reach %s after its current step', this.parent.agent_name)
            : '';
    }
    openParent() {
        openChat(this.chat, this.ui.isSmall(), this.parent.parent_id);
    }
}

composerAccessories.add(SubagentBar);
