// @odoo-module

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';
import { SelectionField } from '@web/views/fields/selection/selection_field';

/** Selection field limited to the values listed in a sibling JSON options field. */
export class FilteredSelectionField extends SelectionField {
    get options() {
        const base = super.options;
        if (!this.props.optionsField) {
            return base;
        }
        const supported = this.props.record.data[this.props.optionsField];
        if (!Array.isArray(supported)) {
            return base;
        }
        const allowed = new Set(supported);
        return base.filter(([value]) => allowed.has(value));
    }
}

// Odoo 16 registers the component itself and reads these as statics on it; the
// field descriptor object and the ``(staticInfo, dynamicInfo)`` signature both
// arrived in 17.0. The options field is named in the arch beside this one, so
// it needs no ``fieldDependencies`` to be loaded with the record.
FilteredSelectionField.props = {
    ...SelectionField.props,
    optionsField: { type: String, optional: true },
};
FilteredSelectionField.defaultProps = {
    ...SelectionField.defaultProps,
    optionsField: '',
};
FilteredSelectionField.extractProps = ({ field, attrs }) => ({
    ...SelectionField.extractProps({ field, attrs }),
    optionsField: attrs.options.options_field || '',
});
FilteredSelectionField.supportedTypes = ['selection'];
FilteredSelectionField.displayName = _t('Filtered Selection');

registry.category('fields').add('filtered_selection', FilteredSelectionField);
