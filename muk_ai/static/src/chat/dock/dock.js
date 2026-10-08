import { Component, untrack, useEffect, usePlugin } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { patch } from '@web/core/utils/patch';

import { ChatHub } from '@mail/core/common/chat_hub_model';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { ChatWindow } from '@muk_ai/chat/window/window';

const DOCK_RIGHT = 16;
const DOCK_WINDOW = 380;
const DOCK_GAP = 10;

/**
 * Return the width the dock takes with some windows open.
 * @param {number} count the open windows
 * @returns {number} the width in pixels, 0 for an empty dock
 */
export function dockWidth(count) {
    return count ? count * DOCK_WINDOW + (count - 1) * DOCK_GAP : 0;
}

/**
 * The floating AI chat windows, docked beside the Discuss chat hub that
 * shares the bottom-right corner.
 */
export class ChatDock extends Component {
    static template = 'muk_ai.ChatDock';
    static components = { ChatWindow };
    chat = usePlugin(AIChatPlugin);
    store = useService('mail.store');
    setup() {
        useEffect(() => {
            void this.chat.windows.length;
            untrack(() => this.store.chatHub.onRecompute());
        });
    }
    /**
     * Measure the width Discuss shows in the corner, from its own layout
     * constants, so the dock sits beside it rather than over it.
     * @returns {number} the width in pixels
     */
    get reserved() {
        const hub = this.store.chatHub;
        if (!hub.canShowOpened.length && !hub.canShowFolded.length) {
            return 0;
        }
        const shown = hub.compact
            ? hub.canShowOpened.filter((window) => window.bypassCompact)
            : hub.canShowOpened;
        const bubbles = hub.BUBBLE_START + hub.BUBBLE + hub.BUBBLE_OUTER * 2;
        return bubbles + shown.length * (hub.WINDOW + hub.WINDOW_INBETWEEN * 2);
    }
    get width() {
        return dockWidth(this.chat.windows.length);
    }
}

registry.category('main_components').add('muk_ai.ChatDock', { Component: ChatDock });

/** Leave the AI dock its room when Discuss decides how many windows fit. */
patch(ChatHub.prototype, {
    get maxOpened() {
        const width = dockWidth(this.store.env.services['muk_ai.chat'].windows.length);
        const slots = width
            ? Math.ceil((DOCK_RIGHT + width) / (this.WINDOW + this.WINDOW_INBETWEEN))
            : 0;
        return Math.max(1, super.maxOpened - slots);
    },
});
