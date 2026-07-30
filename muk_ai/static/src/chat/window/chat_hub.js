import { patch } from '@web/core/utils/patch';

import { ChatHub } from '@mail/core/common/chat_hub_model';

import { DOCK_RIGHT, dockWidth } from '@muk_ai/chat/window/chat_window_service';

/** Let Discuss account for the AI dock, which shares its bottom-right corner. */
patch(ChatHub.prototype, {
    get mukAiDockWidth() {
        const windows = this.store.env.services['muk_ai.chat_window'].state.windows;
        const width = dockWidth(windows.length);
        return width ? DOCK_RIGHT + width : 0;
    },
    get maxOpened() {
        const reserved = this.mukAiDockWidth;
        if (!reserved) {
            return super.maxOpened;
        }
        const slots = Math.ceil(reserved / (this.WINDOW + this.WINDOW_INBETWEEN));
        return Math.max(1, super.maxOpened - slots);
    },
});
