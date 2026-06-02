import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useRecordObserver } from '@web/model/relational_model/utils';
import { AutoComplete } from '@web/core/autocomplete/autocomplete';
import { TagsList } from '@web/core/tags_list/tags_list';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const CATEGORY_COLOR = {
    read: 10,
    write: 2,
};

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
        return [{
            options: (request) => {
                const taken = new Set(this.state.selected);
                const q = (request || '').toLowerCase();
                const matches = this.state.options
                    .filter((o) => !taken.has(o.name) && o.name.toLowerCase().includes(q));
                if (!matches.length) {
                    return [{ label: _t('No matching tool'), unselectable: true, cssClass: 'fst-italic' }];
                }
                return matches.map((o) => ({
                    label: o.name,
                    onSelect: () => this._add(o.name),
                }));
            },
        }];
    }
    onSelect(option) {
        // Odoo 18's AutoComplete requires a top-level onSelect prop and calls
        // it with the chosen source option; we delegate to the per-option
        // onSelect built in autocompleteSources (which 19 invokes directly).
        if (option && typeof option.onSelect === 'function') {
            option.onSelect();
        }
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

export const toolPickerField = {
    component: ToolPickerField,
    displayName: _t('Tool Picker'),
    supportedOptions: [
        {
            label: _t('Options field'),
            name: 'options_field',
            type: 'string',
        },
    ],
    supportedTypes: ['json'],
    extractProps: ({ attrs, options, placeholder }) => ({
        optionsField: options.options_field || '',
        placeholder: placeholder || attrs?.placeholder || '',
    }),
    fieldDependencies: ({ options }) => (
        options.options_field ? [{ name: options.options_field, type: 'json' }] : []
    ),
};

registry.category('fields').add('tool_picker', toolPickerField);
