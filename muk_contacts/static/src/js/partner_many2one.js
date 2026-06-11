/** @odoo-module */

import { markup } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";

const TYPE_ICONS = {
    invoice: "fa-usd",
    delivery: "fa-truck",
    other: "fa-address-book-o",
};

const COMPANY_TYPE_ICONS = {
    company: "fa-building",
    person: "fa-user",
};

function partnerIcon(record) {
    if (record.type && record.type !== "contact") {
        return TYPE_ICONS[record.type] || "fa-address-book-o";
    }
    return COMPANY_TYPE_ICONS[record.company_type] || "fa-user";
}

patch(Many2XAutocomplete.prototype, {
    buildRecordSuggestion(request, record) {
        const suggestion = super.buildRecordSuggestion(request, record);
        if (this.props.resModel === "res.partner") {
            suggestion.label = markup`<i class="fa fa-fw me-1 text-muted ${partnerIcon(record)}"></i>${suggestion.label}`;
        }
        return suggestion;
    },
});
