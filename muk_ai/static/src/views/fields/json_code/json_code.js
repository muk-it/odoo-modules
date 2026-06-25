import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useBus, useService } from '@web/core/utils/hooks';
import { useRecordObserver } from '@web/model/relational_model/utils';
import { CodeEditor } from '@web/core/code_editor/code_editor';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const LINE_HEIGHT = 13;
const VERTICAL_PAD = 4;
const MIN_LINES = 1;

/** Field widget editing a JSON value in an auto-sizing code editor. */
export class JsonCodeField extends Component {
    static template = 'muk_ai.JsonCodeField';
    static props = {
        ...standardFieldProps,
        mode: { type: String, optional: true },
    };
    static defaultProps = {
        mode: 'javascript',
    };
    static components = { CodeEditor };
    setup() {
        this.isDirty = false;
        this.notification = useService('notification');
        this.state = useState({
            initialValue: '',
            lineCount: MIN_LINES,
        });
        useRecordObserver((record) => {
            const stringified = this._stringify(record.data[this.props.name]);
            this.state.initialValue = stringified;
            this.state.lineCount = Math.max(
                MIN_LINES,
                (stringified.match(/\n/g) || []).length + 1,
            );
        });
        const { model } = this.props.record;
        useBus(model.bus, 'WILL_SAVE_URGENTLY', () => this.commitChanges());
        useBus(model.bus, 'NEED_LOCAL_CHANGES', ({ detail }) =>
            detail.proms.push(this.commitChanges()),
        );
    }
    get readonlyHeight() {
        return this.state.lineCount * LINE_HEIGHT + VERTICAL_PAD * 2;
    }
    get wrapperStyle() {
        if (!this.props.readonly) {
            return '';
        }
        return `--mk-json-code-height: ${this.readonlyHeight}px;`;
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
                    _t('Invalid JSON in %(field)s: %(error)s', {
                        field: this.props.string || this.props.name,
                        error: error.message,
                    }),
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
    extractProps: ({ options }) => ({
        mode: options.mode || 'javascript',
    }),
};

registry.category('fields').add('json_code', jsonCodeField);
