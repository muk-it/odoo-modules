import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useBus, useService } from '@web/core/utils/hooks';
import { useRecordObserver } from '@web/model/relational_model/utils';
import { CodeEditor } from '@web/core/code_editor/code_editor';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const PLACEHOLDER_LINE_HEIGHT = 13;
const PLACEHOLDER_MIN_HEIGHT = 156;
const PLACEHOLDER_VERTICAL_PAD = 8;

export class JsonCodeField extends Component {
    static template = 'muk_ai.JsonCodeField';
    static props = {
        ...standardFieldProps,
        mode: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        placeholderField: { type: String, optional: true },
    };
    static defaultProps = {
        mode: 'javascript',
        placeholder: '',
        placeholderField: '',
    };
    static components = { CodeEditor };
    setup() {
        this.isDirty = false;
        this.notification = useService('notification');
        this.state = useState({
            initialValue: '',
            isEmpty: true,
            placeholder: this.props.placeholder,
            editorMinHeight: PLACEHOLDER_MIN_HEIGHT,
        });
        useRecordObserver((record) => {
            const value = record.data[this.props.name];
            const stringified = this._stringify(value);
            this.state.initialValue = stringified;
            this.state.isEmpty = !stringified;
            if (this.props.placeholderField) {
                const dynamic = record.data[this.props.placeholderField];
                this.state.placeholder = dynamic || this.props.placeholder;
            }
            this.state.editorMinHeight = this._heightFor(this.state.placeholder);
        });
        const { model } = this.props.record;
        useBus(model.bus, 'WILL_SAVE_URGENTLY', () => this.commitChanges());
        useBus(model.bus, 'NEED_LOCAL_CHANGES', ({ detail }) =>
            detail.proms.push(this.commitChanges()),
        );
    }
    get editorStyle() {
        return `--mk-json-code-min-height: ${this.state.editorMinHeight}px;`;
    }
    _heightFor(text) {
        if (!text) {
            return PLACEHOLDER_MIN_HEIGHT;
        }
        const lines = (text.match(/\n/g) || []).length + 1;
        return Math.max(
            PLACEHOLDER_MIN_HEIGHT,
            lines * PLACEHOLDER_LINE_HEIGHT + PLACEHOLDER_VERTICAL_PAD * 2,
        );
    }
    _stringify(value) {
        if (value === null || value === undefined || value === false) {
            return '';
        }
        try {
            return JSON.stringify(value, null, 2);
        } catch {
            return String(value);
        }
    }
    handleChange(editedValue) {
        this.isDirty = this.state.initialValue !== editedValue;
        this.state.isEmpty = !editedValue || !editedValue.trim();
        this.props.record.model.bus.trigger('FIELD_IS_DIRTY', this.isDirty);
        this.editedValue = editedValue;
    }
    async commitChanges() {
        if (this.props.readonly || !this.isDirty) {
            return;
        }
        const raw = this.editedValue ?? '';
        let parsed;
        if (!raw.trim()) {
            parsed = false;
        } else {
            try {
                parsed = JSON.parse(raw);
            } catch (error) {
                this.notification.add(
                    _t(
                        'Invalid JSON in %(field)s: %(error)s',
                        { field: this.props.string || this.props.name, error: error.message },
                    ),
                    { type: 'danger', sticky: true },
                );
                await this.props.record.setInvalidField(this.props.name);
                return;
            }
        }
        await this.props.record.resetFieldValidity(this.props.name);
        await this.props.record.update({ [this.props.name]: parsed });
        this.props.record.model.bus.trigger('FIELD_IS_DIRTY', false);
        this.isDirty = false;
    }
}

export const jsonCodeField = {
    component: JsonCodeField,
    displayName: _t('JSON Code Editor'),
    supportedOptions: [
        {
            label: _t('Mode'),
            name: 'mode',
            type: 'string',
        },
    ],
    supportedTypes: ['json'],
    extractProps: ({ attrs, options, placeholder }) => ({
        mode: options.mode || 'javascript',
        placeholder: placeholder || attrs?.placeholder || '',
        placeholderField: options.placeholder_field || '',
    }),
    fieldDependencies: ({ options }) => (
        options.placeholder_field ? [{ name: options.placeholder_field, type: 'char' }] : []
    ),
};

registry.category('fields').add('json_code', jsonCodeField);
