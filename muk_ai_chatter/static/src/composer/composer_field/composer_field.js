/** @odoo-module */

import { Component, useRef } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

export const OPEN_EVENT = 'muk-ai-compose-open';

/**
 * Button of the full composer's footer opening the writing helper of the
 * dialog's editor, with its cursor, selection and record.
 */
export class ComposerFieldAI extends Component {
    static template = 'muk_ai_chatter.ComposerFieldAI';
    static props = standardFieldProps;
    setup() {
        this.button = useRef('button');
    }
    onClick() {
        this.button.el
            .closest('.o_dialog, .modal')
            ?.querySelector('.odoo-editor-editable')
            ?.dispatchEvent(new CustomEvent(OPEN_EVENT));
    }
}

registry.category('fields').add('mail_composer_muk_ai', ComposerFieldAI);
