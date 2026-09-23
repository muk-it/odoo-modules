import { Component, signal, t, useProps } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { isHtmlEmpty } from '@web/core/utils/html';
import { usePopover } from '@web/core/popover/popover_hook';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

/** Popover body showing the full, selectable text of a field value. */
export class TextValuePopover extends Component {
    static template = 'muk_web_utils.TextValuePopover';
    props = useProps({
        close: t.function(),
        value: t.any(),
    });
}

/** Field that displays an icon for textual values and reveals the text in a popover. */
export class TextIconField extends Component {
    static template = 'muk_web_utils.TextIconField';
    props = useProps({
        ...standardFieldProps,
        icon: t.string().optional('description'),
    });
    iconRef = signal.ref();
    popover = usePopover(TextValuePopover);
    get hasValue() {
        return !isHtmlEmpty(this.props.record.data[this.props.name] || '');
    }
    showValue() {
        this.popover.open(this.iconRef(), {
            value: this.props.record.data[this.props.name],
        });
    }
}

export const textIconField = {
    component: TextIconField,
    listViewWidth: ({ hasLabel }) => (!hasLabel ? 20 : false),
    supportedOptions: [
        {
            label: 'Icon',
            name: 'icon',
            type: 'string',
        },
    ],
    supportedTypes: ['html', 'text', 'char'],
    extractProps: ({ options }) => ({
        icon: options.icon,
    }),
};

registry.category('fields').add('text_icon', textIconField);
