/** @odoo-module */

import { patch } from '@web/core/utils/patch';

import { SuggestionService } from '@mail/core/common/suggestion_service';
import { cleanTerm } from '@mail/utils/common/format';

patch(SuggestionService.prototype, {
    /**
     * Offer the AI agents first in every Discuss conversation and nowhere
     * else. An agent is never a recipient, so a private one leaks nothing.
     * @override
     */
    searchPartnerSuggestions(cleanedSearchTerm, thread, sort) {
        const result = super.searchPartnerSuggestions(...arguments);
        const keep = (partner) => !partner.is_ai_agent;
        result.mainSuggestions = result.mainSuggestions.filter(keep);
        result.extraSuggestions = result.extraSuggestions.filter(keep);
        if (
            thread?.model !== 'discuss.channel' ||
            !this.store.self?.user?.isInternalUser
        ) {
            return result;
        }
        const agents = Object.values(this.store.Persona.records).filter(
            (persona) =>
                persona.type === 'partner' &&
                persona.is_ai_agent &&
                cleanTerm(persona.name || '').includes(cleanedSearchTerm),
        );
        result.mainSuggestions = [
            ...(sort
                ? this.sortPartnerSuggestions(agents, cleanedSearchTerm, thread)
                : agents),
            ...result.mainSuggestions,
        ];
        return result;
    },
});
