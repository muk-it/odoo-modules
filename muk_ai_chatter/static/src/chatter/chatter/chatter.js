/** @odoo-module */

import { registerPatch } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';

registerPatch({
    name: 'Chatter',
    fields: {
        aiSessionsOpen: attr({ default: false }),
        aiSessionTotal: attr({ default: 0 }),
    },
    recordMethods: {
        /**
         * Show the count of the sessions the box found on the record.
         * @param {number} total the sessions linked to the record
         */
        onAISessionsLoaded(total) {
            if (this.exists()) {
                this.update({ aiSessionTotal: total });
            }
        },
        onClickAISessions() {
            this.update({ aiSessionsOpen: !this.aiSessionsOpen });
        },
    },
});
