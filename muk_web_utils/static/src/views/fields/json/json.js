import { t, useProps } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { JsonField, jsonField } from '@web/views/fields/json/json_field';

/** Json field that pretty-prints its value with indentation when ``prettify`` is set. */
export class PrettyJsonField extends JsonField {
    static template = 'muk_web_utils.PrettyJsonField';
    props = useProps({
        ...standardFieldProps,
        prettify: t.boolean().optional(false),
    });
    get formattedValue() {
        const value = this.props.record.data[this.props.name];
        if (value && this.props.prettify) {
            return JSON.stringify(value, null, 4);
        }
        return super.formattedValue;
    }
}

patch(jsonField, {
    component: PrettyJsonField,
    extractProps: ({ options }) => ({
        prettify: !!options.prettify,
    }),
});
