import { patch } from '@web/core/utils/patch';

import { AIChat } from '@muk_ai/chat/chat';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';
import { ChatWindow } from '@muk_ai/chat/window/chat_window';
import { patchChatSurfaces } from '@muk_ai/chat/surfaces';

import { SubagentRunStrip } from '@muk_ai_subagents/chat/agents/run_strip';
import { SubagentChildView } from '@muk_ai_subagents/chat/child/child_view';
import { SubagentEscalations } from '@muk_ai_subagents/chat/escalation/escalation_card';
import {
    subagentPlaceholder,
    useSubagentRun,
} from '@muk_ai_subagents/chat/run/run_store';
import '@muk_ai_subagents/chat/turns/subagent_turns';
import '@muk_ai_subagents/chat/tools/tool_card';

const SUBAGENT_COMPONENTS = {
    SubagentEscalations,
    SubagentRunStrip,
    SubagentChildView,
};

AIChat.components = { ...AIChat.components, ...SUBAGENT_COMPONENTS };
ChatWindow.components = { ...ChatWindow.components, ...SUBAGENT_COMPONENTS };

/**
 * Keep the run roster loaded and say who the one composer is writing to.
 *
 * Where a message goes is the session's business, so that every way of sending
 * agrees on it; what is left here is what the composer shows.
 * @returns {object} the patch for a component that owns a chat and a composer
 */
const composerRouting = () => ({
    setup() {
        super.setup();
        useSubagentRun(this.session);
    },
    get inputPlaceholder() {
        return subagentPlaceholder(this.session) || super.inputPlaceholder;
    },
    get isQueueing() {
        // A steer lands at the subagent's next step and never mid-thought, so
        // the composer offers Queue rather than the parent's Stop.
        return !!this.session.state.subagentOpen || super.isQueueing;
    },
});

patchChatSurfaces(composerRouting);

/**
 * Keep subagents out of the chat list and its running count.
 *
 * A subagent is a session owned by the same user, so without this it turns
 * up in the systray beside the conversations the user actually started.
 */
patch(MukAISystray.prototype, {
    get sessionDomain() {
        return [...super.sessionDomain, ['parent_session_id', '=', false]];
    },
});

/**
 * Keep subagents out of the sidebar, including when it is searched.
 *
 * Typing a word a subagent happens to carry would otherwise offer it as a
 * chat to open, which is the one place a child is not meant to be reached
 * from — a subagent is opened from the run it belongs to.
 */
patch(AIChat.prototype, {
    get baseSessionsDomain() {
        return [...super.baseSessionsDomain, ['parent_session_id', '=', false]];
    },
});
