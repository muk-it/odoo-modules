import '@mail/chatter/web/chatter_patch';

import { patch } from '@web/core/utils/patch';

import { Chatter } from '@mail/chatter/web_portal_project/chatter';

import { AISessionBox } from '@muk_ai_chatter/chatter/session_box/session_box';

Object.assign(Chatter.components, { AISessionBox });

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.aiSessionTotal = 0;
    },
    toggleAISessions() {
        this.state.activePanel =
            this.state.activePanel === 'AI_SESSIONS' ? 'NONE' : 'AI_SESSIONS';
    },
});
