import { markup } from '@odoo/owl';
import { patch } from '@web/core/utils/patch';
import { Many2XAutocomplete } from '@web/views/fields/relational_utils';

const TYPE_ICONS = {
    invoice: 'fa-usd',
    delivery: 'fa-truck',
    other: 'fa-address-book-o',
};

const COMPANY_TYPE_ICONS = {
    company: 'fa-building',
    person: 'fa-user',
};

/**
 * Pick the Font Awesome icon class for a partner suggestion from its address
 * type, falling back to its company type.
 * @param {object} record the partner record carrying type and company_type
 * @returns {string} the Font Awesome icon class
 */
function partnerIcon(record) {
    if (record.type && record.type !== 'contact') {
        return TYPE_ICONS[record.type] || 'fa-address-book-o';
    }
    return COMPANY_TYPE_ICONS[record.company_type] || 'fa-user';
}

/** Prefix res.partner autocomplete suggestions with a partner type icon. */
patch(Many2XAutocomplete.prototype, {
    /**
     * Build a suggestion and, for res.partner, prepend its partner type icon.
     * @param {object} request the autocomplete request
     * @param {object} record the partner record being suggested
     * @returns {object} the suggestion descriptor
     */
    buildRecordSuggestion(request, record) {
        const suggestion = super.buildRecordSuggestion(request, record);
        if (this.props.resModel === 'res.partner') {
            suggestion.label = markup`<i class="fa fa-fw me-1 text-muted ${partnerIcon(
                record,
            )}"></i>${suggestion.label}`;
        }
        return suggestion;
    },
});
