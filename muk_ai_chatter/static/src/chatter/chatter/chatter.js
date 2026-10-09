import { patch } from '@web/core/utils/patch';

import { Chatter } from '@mail/chatter/web_portal/chatter';

import { AISessionBox } from '@muk_ai_chatter/chatter/session_box/session_box';

Object.assign(Chatter.components, { AISessionBox });

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        Object.assign(this.state, { aiSessionsOpen: false, aiSessionTotal: 0 });
    },
    toggleAISessions() {
        this.state.aiSessionsOpen = !this.state.aiSessionsOpen;
    },
});
