import { Component, useRef } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { OPEN_EVENT } from '@muk_ai_chatter/composer/compose_plugin';

/**
 * Offer the writing helper from the full composer's button row.
 *
 * The row sits outside the editor, so the button does not open a panel of its
 * own: it tells the editable to open the one the toolbar opens, which is what
 * keeps the cursor, the selection and the record the same wherever the helper
 * is asked for.
 */
export class ComposerFieldAI extends Component {
    static template = 'muk_ai_chatter.ComposerFieldAI';
    static props = { ...standardFieldProps };

    setup() {
        this.buttonRef = useRef('button');
    }
    onClick() {
        const dialog = this.buttonRef.el?.closest('.o_dialog, .modal');
        const editable = dialog?.querySelector('.odoo-editor-editable');
        editable?.dispatchEvent(new CustomEvent(OPEN_EVENT));
    }
}

registry.category('fields').add('mail_composer_muk_ai', {
    component: ComposerFieldAI,
});
