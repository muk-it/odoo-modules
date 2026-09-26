import { markup } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { Many2XAutocomplete } from '@web/views/fields/relational_utils';

const KIND_ICONS = {
    company: 'business',
    person: 'person',
    invoice: 'description',
    delivery: 'local_shipping',
    other: 'deployed_code',
};

/** Prefix res.partner autocomplete suggestions with the icon of their kind. */
patch(Many2XAutocomplete.prototype, {
    get searchSpecification() {
        const specification = super.searchSpecification;
        if (this.props.resModel === 'res.partner') {
            return { ...specification, contact_kind: {} };
        }
        return specification;
    },
    buildRecordSuggestion(request, record) {
        const suggestion = super.buildRecordSuggestion(request, record);
        if (this.props.resModel === 'res.partner') {
            const icon = KIND_ICONS[record.contact_kind] || KIND_ICONS.person;
            suggestion.label = markup`<i class="oi oi-fw me-1 text-muted" data-icon="${icon}"></i>${suggestion.label}`;
        }
        return suggestion;
    },
});
