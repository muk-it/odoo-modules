import { t, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import {
    SelectionField,
    selectionField,
    selectionFieldProps,
} from '@web/views/fields/selection/selection_field';

/** Selection field limited to the values a sibling JSON field lists. */
export class FilteredSelectionField extends SelectionField {
    props = useProps({ ...selectionFieldProps, optionsField: t.string().optional('') });
    get options() {
        const allowed = this.props.record.data[this.props.optionsField];
        return Array.isArray(allowed)
            ? super.options.filter(([value]) => allowed.includes(value))
            : super.options;
    }
}

registry.category('fields').add('filtered_selection', {
    ...selectionField,
    component: FilteredSelectionField,
    displayName: _t('Filtered Selection'),
    supportedOptions: [
        { label: _t('Options field'), name: 'options_field', type: 'string' },
    ],
    supportedTypes: ['selection'],
    extractProps: (staticInfo, dynamicInfo) => ({
        ...selectionField.extractProps(staticInfo, dynamicInfo),
        optionsField: staticInfo.options.options_field || '',
    }),
    fieldDependencies: ({ options }) =>
        options.options_field ? [{ name: options.options_field, type: 'json' }] : [],
});
