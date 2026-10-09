/** @odoo-module */

import { registerPatch } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';
import { cleanSearchTerm } from '@mail/utils/utils';

/**
 * Tell whether the AI agents are offered in a thread: every Discuss
 * conversation, to staff, and nowhere else. An agent is never a recipient, so
 * a private conversation leaks nothing to it.
 * @param {object} messaging the messaging record
 * @param {object} [thread] the thread the composer writes in
 * @returns {boolean} whether the agents are suggested there
 */
function offersAgents(messaging, thread) {
    return Boolean(
        thread?.model === 'mail.channel' && messaging.currentUser?.isInternalUser,
    );
}

registerPatch({
    name: 'Partner',
    fields: {
        is_ai_agent: attr({ default: false }),
    },
    modelMethods: {
        async fetchSuggestions(searchTerm, { thread } = {}) {
            await this._super(...arguments);
            if (!offersAgents(this.messaging, thread)) {
                return;
            }
            const agents = await this.messaging.rpc(
                {
                    model: 'res.partner',
                    method: 'get_ai_mention_suggestions',
                    kwargs: { channel_id: thread.id, search: searchTerm },
                },
                { shadow: true },
            );
            this.messaging.models['Partner'].insert(agents);
        },
        getSuggestionSortFunction() {
            const sort = this._super(...arguments);
            return (a, b) =>
                Number(b.is_ai_agent) - Number(a.is_ai_agent) || sort(a, b);
        },
        searchSuggestions(searchTerm, { thread } = {}) {
            const [main, extra] = this._super(...arguments);
            if (!offersAgents(this.messaging, thread)) {
                return [main, extra];
            }
            const cleanedSearchTerm = cleanSearchTerm(searchTerm);
            const agents = this.messaging.models['Partner'].all(
                (partner) =>
                    partner.is_ai_agent &&
                    cleanSearchTerm(partner.name || '').includes(cleanedSearchTerm),
            );
            return [[...agents, ...main], extra];
        },
    },
});
