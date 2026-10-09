import '@mail/discuss/core/common/suggestion_service_patch';

import { registry } from '@web/core/registry';
import { patch } from '@web/core/utils/patch';

import { SuggestionService } from '@mail/core/common/suggestion_service';

registry.category('mail.partner_compare').add(
    'muk_ai_chatter.agents-first',
    (p1, p2) => {
        if (!p1.is_ai_agent === !p2.is_ai_agent) {
            return undefined;
        }
        return p1.is_ai_agent ? -1 : 1;
    },
    { sequence: 1 },
);

patch(SuggestionService.prototype, {
    /**
     * Offer the AI agents in every Discuss conversation and nowhere else. An
     * agent is never a recipient, so a private conversation leaks nothing.
     * @override
     */
    getPartnerSuggestions(thread) {
        const suggestions = [...super.getPartnerSuggestions(...arguments)].filter(
            (partner) => !partner.is_ai_agent,
        );
        if (thread?.model !== 'discuss.channel' || !this.store.self.isInternalUser) {
            return suggestions;
        }
        const agents = Object.values(this.store.Persona.records).filter(
            (persona) => persona.type === 'partner' && persona.is_ai_agent,
        );
        return [...suggestions, ...agents];
    },
});
