import { useEffect } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import { AIChat } from '@muk_ai/chat/chat/chat';
import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    agentSuggestions,
    ChatConversation,
} from '@muk_ai/chat/conversation/conversation';

const extension =
    window.parent !== window ? window.location.ancestorOrigins?.[0] : undefined;
const embedded = Boolean(extension?.startsWith('chrome-extension://'));

if (embedded) {
    document.documentElement.classList.add('mk_browser_embed');
}

/**
 * Suggestions about the page open in the browser, shaped like an agent's.
 * @returns {object[]} `{label, prompt, preview}` entries
 */
function pageSuggestions() {
    return agentSuggestions({
        suggestions: [
            {
                label: _t('This page'),
                prompt: _t(
                    'Read the page open in my browser, tell me in a few lines what it is about and what I could do with it in Odoo.',
                ),
            },
            {
                label: _t('Product'),
                prompt: _t(
                    'Create a product in Odoo from the product on this page, with its name, price and description. Ask me before anything else.',
                ),
            },
            {
                label: _t('Contact'),
                prompt: _t(
                    'Find the company or person on this page in Odoo and show me what we have on them. Offer to create them if they are missing.',
                ),
            },
            {
                label: _t('Form'),
                prompt: _t(
                    'Fill the form on this page with the matching data from Odoo. Ask me which record to use, and do not submit it.',
                ),
            },
        ],
    });
}

patch(AIChat.prototype, {
    setup() {
        super.setup();
        if (embedded) {
            useEffect(() => {
                window.parent.postMessage(
                    { type: 'muk_ai_browser.chat', id: this.state.sessionId },
                    extension,
                );
            });
        }
    },
    get suggestions() {
        return embedded ? pageSuggestions() : super.suggestions;
    },
});

patch(AIChatPlugin.prototype, {
    async runAction(session, action) {
        if (embedded && action?.type === 'ir.actions.act_window' && action.res_id) {
            window.parent.postMessage(
                {
                    type: 'muk_ai_browser.show',
                    path: `/odoo/${action.res_model}/${action.res_id}`,
                },
                extension,
            );
            return;
        }
        return super.runAction(session, action);
    },
});

patch(ChatConversation.prototype, {
    get suggestions() {
        return embedded ? pageSuggestions() : super.suggestions;
    },
});
