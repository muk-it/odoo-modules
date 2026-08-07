import { registry } from '@web/core/registry';

/**
 * Sort AI agents to the top of the @ list.
 *
 * The stand-in contact of an agent is archived so it stays out of the address
 * book, and Odoo sorts archived personas last — which would bury the one
 * suggestion the user typed `@` for. This runs ahead of that rule.
 */
registry.category('mail.partner_compare').add(
    'muk_ai_chatter.agents-first',
    (p1, p2) => {
        const isAgent1 = Boolean(p1.is_ai_agent);
        const isAgent2 = Boolean(p2.is_ai_agent);
        if (isAgent1 !== isAgent2) {
            return isAgent1 ? -1 : 1;
        }
        return undefined;
    },
    { sequence: 1 },
);
