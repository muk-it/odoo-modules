// @odoo-module

import { patch } from '@web/core/utils/patch';

import { AIChat } from '@muk_ai/chat/chat';
import { ChatWindow } from '@muk_ai/chat/window/chat_window';

/**
 * Patch both surfaces that render a chat, with an object of their own each.
 *
 * `patch` re-points the patch object's prototype at its target to make
 * `super` work, so passing one object to both would rewire the first
 * surface's prototype chain through the second.
 * @param {Function} build returns a fresh patch object each call
 */
export function patchChatSurfaces(build) {
    patch(AIChat.prototype, build());
    patch(ChatWindow.prototype, build());
}
