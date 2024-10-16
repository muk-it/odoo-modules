import { registry } from '@web/core/registry';
import { exprToBoolean } from '@web/core/utils/strings';

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
    listViewWidth: ({ hasLabel }) => (!hasLabel ? 20 : false),
    supportedOptions: [
        {
            label: 'Icons',
            name: 'icons',
            type: 'string',
        },
    ],
    extractProps({ attrs, options }) {
        const props = selectionField.extractProps(...arguments);
        props.noLabel = exprToBoolean(attrs.nolabel);
        props.icons = options.icons;
        return props;
    },
};

registry.category('fields').add('selection_icons', selectionIconsField);
