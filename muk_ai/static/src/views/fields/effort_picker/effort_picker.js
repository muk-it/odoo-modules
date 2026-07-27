// @odoo-module

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';
import { SelectionField } from '@web/views/fields/selection/selection_field';

/** Selection field limited to the tiers listed in a JSON options field. */
export class EffortPickerField extends SelectionField {
    static props = {
        ...SelectionField.props,
        optionsField: { type: String, optional: true },
    };
    static defaultProps = {
        ...SelectionField.defaultProps,
        optionsField: '',
    };
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
        return base.filter(([tier]) => allowed.has(tier));
    }
}

// Odoo 16 reads these as statics on the component and calls extractProps with a
// single ``{field, attrs}`` argument; the field descriptor object and the
// ``(staticInfo, dynamicInfo)`` signature both arrived in 17.0. The options
// field is declared explicitly in the views, so no fieldDependencies hook.
EffortPickerField.extractProps = ({ attrs }) => ({
    ...SelectionField.extractProps({ attrs }),
    optionsField: attrs.options.options_field || '',
});
EffortPickerField.supportedTypes = ['selection'];
EffortPickerField.displayName = _t('Effort Picker');

registry.category('fields').add('effort_picker', EffortPickerField);
