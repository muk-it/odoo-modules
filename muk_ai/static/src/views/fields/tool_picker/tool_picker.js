// @odoo-module

import { Component, useState } from '@odoo/owl';

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';
import { useRecordObserver } from '@muk_ai/core/compat/record_observer';
import { AutoComplete } from '@web/core/autocomplete/autocomplete';
import { TagsList } from '@web/views/fields/many2many_tags/tags_list';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const CATEGORY_COLOR = {
    read: 10,
    write: 2,
};

/** Field widget picking tool names from the catalog as colour-coded tags. */
export class ToolPickerField extends Component {
    static template = 'muk_ai.ToolPickerField';
    static components = { AutoComplete, TagsList };
    static props = {
        ...standardFieldProps,
        optionsField: { type: String, optional: true },
        placeholder: { type: String, optional: true },
    };
    static defaultProps = {
        optionsField: '',
        placeholder: '',
    };
    setup() {
        this.state = useState({
            selected: [],
            options: [],
        });
        useRecordObserver((record) => {
            const value = record.data[this.props.name];
            this.state.selected = Array.isArray(value) ? [...value] : [];
            if (this.props.optionsField) {
                const opts = record.data[this.props.optionsField];
                this.state.options = Array.isArray(opts) ? opts : [];
            }
        });
    }
    _option(name) {
        return this.state.options.find((o) => o.name === name);
    }
    get tagListItems() {
        return this.state.selected.map((name) => {
            const opt = this._option(name);
            const known = !!opt;
            return {
                id: name,
                text: name,
                colorIndex: known ? CATEGORY_COLOR[opt.category] || 0 : 1,
                onDelete: this.props.readonly ? undefined : () => this._remove(name),
            };
        });
    }
    get autocompleteSources() {
        return [
            {
                options: (request) => {
                    const taken = new Set(this.state.selected);
                    const q = (request || '').toLowerCase();
                    const matches = this.state.options.filter(
                        (o) => !taken.has(o.name) && o.name.toLowerCase().includes(q),
                    );
                    if (!matches.length) {
                        return [
                            {
                                label: _t('No matching tool'),
                                unselectable: true,
                                classList: 'fst-italic',
                            },
                        ];
                    }
                    return matches.map((o) => ({
                        label: o.name,
                        name: o.name,
                    }));
                },
            },
        ];
    }
    onSelectTool(option) {
        return this._add(option.name);
    }
    async _add(name) {
        if (this.state.selected.includes(name)) {
            return;
        }
        this.state.selected = [...this.state.selected, name];
        await this._commit();
    }
    async _remove(name) {
        this.state.selected = this.state.selected.filter((n) => n !== name);
        await this._commit();
    }
    async _commit() {
        await this.props.record.update({
            [this.props.name]: this.state.selected.length ? this.state.selected : false,
        });
    }
}

// Odoo 16 reads these as statics on the component and calls extractProps with a
// single ``{field, attrs}`` argument; the field descriptor object and the
// ``(staticInfo, dynamicInfo)`` signature both arrived in 17.0. The options
// field is declared explicitly in the views, so no fieldDependencies hook.
ToolPickerField.extractProps = ({ attrs }) => ({
    optionsField: attrs.options.options_field || '',
    placeholder: attrs.placeholder || '',
});
ToolPickerField.supportedTypes = ['json'];
ToolPickerField.displayName = _t('Tool Picker');

registry.category('fields').add('tool_picker', ToolPickerField);
