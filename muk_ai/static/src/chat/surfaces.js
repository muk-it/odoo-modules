// @odoo-module

import { patch } from '@web/core/utils/patch';

import { AIChat } from '@muk_ai/chat/chat';
import { ChatWindow } from '@muk_ai/chat/window/chat_window';

/**
 * Patch both surfaces that render a chat, with an object of their own each.
 *
 * `patch` re-points the patch object's prototype at its target to make
 * `super` work, so passing one object to both would rewire the first
 * surface's prototype chain through the second. This Odoo also names every
 * patch, and a name may only be used once per target.
 * @param {string} name identifies the patch, usually the addon's own name
 * @param {Function} build returns a fresh patch object each call
 */
export function patchChatSurfaces(name, build) {
    patch(AIChat.prototype, `${name}.chat`, build());
    patch(ChatWindow.prototype, `${name}.window`, build());
}
