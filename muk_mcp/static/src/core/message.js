/** @odoo-module **/

import { registerFieldPatchModel } from '@mail/model/model_core';
import { attr } from '@mail/model/model_field';

registerFieldPatchModel('mail.message', 'muk_mcp/static/src/core/message.js', {
    mcp_name: attr({
        default: '',
    }),
});
