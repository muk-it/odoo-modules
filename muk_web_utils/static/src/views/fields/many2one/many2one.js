// @odoo-module

import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";

import { many2OneField } from "@web/views/fields/many2one/many2one_field";

patch(many2OneField, {
    extractProps({ options }) {
        let res = super.extractProps(...arguments);
        if (
            session.disable_quick_create &&
            options.no_quick_create == undefined
        ) {
            res.canQuickCreate = false;
        }
        return res;
    }
});
