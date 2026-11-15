import { onMounted, useEffect } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';
import { actionService } from '@web/webclient/actions/action_service';

import { AIChat } from '@muk_ai/chat/chat';
import { agentSuggestions } from '@muk_ai/chat/utils';

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
        agents: [
            {
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
            },
        ],
    });
}

patch(AIChat.prototype, {
    setup() {
        super.setup();
        if (!embedded) {
            return;
        }
        this.browserStart = !this._getRequestedSessionId();
        useEffect(
            (id) => {
                window.parent.postMessage(
                    { type: 'muk_ai_browser.chat', id },
                    extension,
                );
            },
            () => [this.session.state.sessionId],
        );
        onMounted(() => {
            if (this.browserStart) {
                this.browserStart = false;
                this.onNewSession();
            }
        });
    },
    get suggestions() {
        return embedded ? pageSuggestions() : super.suggestions;
    },
    /**
     * Start the browser panel on the latest chat while it is empty, else on a new one.
     * @param {number} sessionId the chat to show
     */
    async _selectSession(sessionId) {
        if (!this.browserStart) {
            return super._selectSession(sessionId);
        }
        this.browserStart = false;
        const used = await this.orm.searchCount('muk_ai.session', [
            ['id', '=', sessionId],
            ['event_ids', '!=', false],
        ]);
        return used ? this.onNewSession() : super._selectSession(sessionId);
    },
});

if (embedded) {
    patch(actionService, {
        start() {
            const manager = super.start(...arguments);
            const doAction = manager.doAction;
            manager.doAction = (action, options) => {
                if (action?.type === 'ir.actions.act_window' && action.res_id) {
                    window.parent.postMessage(
                        {
                            type: 'muk_ai_browser.show',
                            path: `/odoo/${action.res_model}/${action.res_id}`,
                        },
                        extension,
                    );
                    return Promise.resolve(true);
                }
                return doAction(action, options);
            };
            return manager;
        },
    });
}
