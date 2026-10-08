import { Component, t, useProps, usePlugin } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import { AIChatPlugin, useAISession } from '@muk_ai/core/chat_plugin/chat_plugin';
import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import { SessionPills } from '@muk_ai/chat/pills/pills';
import { SessionStatus } from '@muk_ai/chat/status/status';
import { UsageMeter } from '@muk_ai/chat/usage/usage';

/** Floating window showing one chat. */
export class ChatWindow extends Component {
    static template = 'muk_ai.ChatWindow';
    static components = {
        ChatConversation,
        SessionPills,
        SessionStatus,
        UsageMeter,
    };
    props = useProps({ id: t.number(), minimized: t.boolean().optional(false) });
    chat = usePlugin(AIChatPlugin);
    session = useAISession(() => this.props.id);
    placeholder = _t('Message...');
    get toggleTitle() {
        return this.props.minimized ? _t('Expand') : _t('Minimize');
    }
    openFullChat() {
        this.chat.closeWindow(this.props.id);
        this.chat.openFullChat(this.props.id);
    }
}
