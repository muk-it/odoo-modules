import { patch } from '@web/core/utils/patch';

import { Thread } from '@mail/core/common/thread_model';
import '@mail/core/web/thread_model_patch';

/** Open the messages of an AI chat, from the inbox and anywhere else, in the AI chat. */
patch(Thread.prototype, {
    get openRecordActionRequest() {
        if (this.model === 'muk_ai.session') {
            return {
                type: 'ir.actions.client',
                tag: 'muk_ai.chat',
                params: { session_id: this.id },
            };
        }
        return super.openRecordActionRequest;
    },
});
