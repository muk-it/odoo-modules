import { Component, t, useProps } from '@odoo/owl';

import { AutoComplete } from '@web/core/autocomplete/autocomplete';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { BadgeTag } from '@web/core/tags_list/badge_tag';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const CATEGORY_COLORS = { read: 10, write: 2 };

/** JSON field picking tool names of the catalogue as tags coloured by category. */
export class ToolPickerField extends Component {
    static template = 'muk_ai.ToolPickerField';
    static components = { AutoComplete, BadgeTag };
    props = useProps({
        ...standardFieldProps,
        optionsField: t.string().optional(''),
        placeholder: t.string().optional(''),
    });
    get selected() {
        const value = this.props.record.data[this.props.name];
        return Array.isArray(value) ? value : [];
    }
    get options() {
        const options = this.props.record.data[this.props.optionsField];
        return Array.isArray(options) ? options : [];
    }
    color(name) {
        const option = this.options.find((item) => item.name === name);
        return option ? CATEGORY_COLORS[option.category] || 0 : 1;
    }
    get sources() {
        return [
            {
                options: (request) => {
                    const query = (request || '').toLowerCase();
                    const matches = this.options.filter(
                        (option) =>
                            !this.selected.includes(option.name) &&
                            option.name.toLowerCase().includes(query),
                    );
                    return matches.length
                        ? matches.map((option) => ({
                              label: option.name,
                              onSelect: () =>
                                  this.commit([...this.selected, option.name]),
                          }))
                        : [{ label: _t('No matching tool'), cssClass: 'fst-italic' }];
                },
            },
        ];
    }
    commit(names) {
        return this.props.record.update({
            [this.props.name]: names.length ? names : false,
        });
    }
}

registry.category('fields').add('tool_picker', {
    component: ToolPickerField,
    displayName: _t('Tool Picker'),
    supportedOptions: [
        { label: _t('Options field'), name: 'options_field', type: 'string' },
    ],
    supportedTypes: ['json'],
    extractProps: ({ attrs, options, placeholder }) => ({
        optionsField: options.options_field || '',
        placeholder: placeholder || attrs?.placeholder || '',
    }),
    fieldDependencies: ({ options }) =>
        options.options_field ? [{ name: options.options_field, type: 'json' }] : [],
});
