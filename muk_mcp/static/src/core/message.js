/** @odoo-module **/

import { registerPatch } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';

registerPatch({
    name: 'Message',
    fields: {
        mcp_name: attr({
            default: '',
        }),
    },
});
