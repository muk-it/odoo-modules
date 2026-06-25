import { registry } from '@web/core/registry';
import { exprToBoolean } from '@web/core/utils/strings';

import {
    SelectionField,
    selectionField,
} from '@web/views/fields/selection/selection_field';

/** Selection field that renders each value as a configurable icon instead of text. */
export class SelectionIconsField extends SelectionField {
    static template = 'muk_web_utils.SelectionIconsField';
    static props = {
        ...SelectionField.props,
        icons: { type: Object },
        defaultIcon: { type: String, optional: true },
        noLabel: { type: Boolean, optional: true },
    };
    valueIcon(value) {
        const icon = this.props.icons && this.props.icons[value];
        return icon || this.props.defaultIcon || '';
    }
}

export const selectionIconsField = {
    ...selectionField,
    component: SelectionIconsField,
    supportedTypes: ['selection'],
    listViewWidth: ({ hasLabel }) => (!hasLabel ? 20 : false),
    supportedOptions: [
        {
            label: 'Icons',
            name: 'icons',
            type: 'string',
        },
        {
            label: 'Default Icon',
            name: 'defaultIcon',
            type: 'string',
        },
    ],
    extractProps({ attrs, options }) {
        const props = selectionField.extractProps(...arguments);
        props.noLabel = exprToBoolean(attrs.nolabel);
        props.defaultIcon = options.defaultIcon;
        props.icons = options.icons;
        return props;
    },
};

registry.category('fields').add('selection_icons', selectionIconsField);
