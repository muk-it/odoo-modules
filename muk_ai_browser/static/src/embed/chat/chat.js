/** @odoo-module */

import { useEffect } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { actionService } from '@web/webclient/actions/action_service';

import { _t } from '@muk_ai/core/compat/translation';
import { AIChat } from '@muk_ai/chat/chat';
import { agentSuggestions } from '@muk_ai/chat/utils';
import { chatWindowService } from '@muk_ai/chat/window/chat_window_service';

const extension =
    window.parent !== window ? window.location.ancestorOrigins?.[0] : undefined;
const embedded = Boolean(extension?.startsWith('chrome-extension://'));

if (embedded) {
    document.documentElement.classList.add('mk_browser_embed');
}

/**
 * Suggestions about the page open in the browser, shaped like an agent's.
 * @returns {object[]} `{label, prompt}` entries
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

patch(AIChat.prototype, 'muk_ai_browser', {
    setup() {
        this._super(...arguments);
        if (embedded) {
            useEffect(
                (id) => {
                    window.parent.postMessage(
                        { type: 'muk_ai_browser.chat', id },
                        extension,
                    );
                },
                () => [this.session.state.sessionId],
            );
        }
    },
    get suggestions() {
        return embedded ? pageSuggestions() : this._super();
    },
});

patch(actionService, 'muk_ai_browser', {
    start(env) {
        const actions = this._super(env);
        if (embedded) {
            const doAction = actions.doAction;
            actions.doAction = (action, options) => {
                if (action?.type === 'ir.actions.act_window' && action.res_id) {
                    window.parent.postMessage(
                        {
                            type: 'muk_ai_browser.show',
                            path: `/web#id=${action.res_id}&model=${action.res_model}&view_type=form`,
                        },
                        extension,
                    );
                    return Promise.resolve();
                }
                return doAction(action, options);
            };
        }
        return actions;
    },
});

patch(chatWindowService, 'muk_ai_browser', {
    start(env) {
        const windows = this._super(env);
        if (embedded) {
            windows.open = () => {};
        }
        return windows;
    },
});
