// @odoo-module

import { registry } from '@web/core/registry';
import { archParseBoolean } from '@web/views/utils';

import { SelectionField, selectionField } from '@web/views/fields/selection/selection_field';

export class SelectionIconsField extends SelectionField {
    static template = 'muk_web_utils.SelectionIconsField';
    static props = {
        ...SelectionField.props,
        icons: { type: Object },
        noLabel: { type: Boolean, optional: true },
    };
    valueIcon(value) {
        return this.props.icons && this.props.icons[value] || '';
    }
}

export const selectionIconsField = {
    ...selectionField,
    component: SelectionIconsField,
    supportedTypes: ['selection'],
    supportedOptions: [
        {
            label: 'Icons',
            name: 'icons',
            type: 'string',
        },
    ],
    extractProps({ attrs, options }) {
        const props = selectionField.extractProps(...arguments);
        props.noLabel = archParseBoolean(attrs.nolabel);
        props.icons = options.icons;
        return props;
    },
};

registry.category('fields').add('selection_icons', selectionIconsField);
