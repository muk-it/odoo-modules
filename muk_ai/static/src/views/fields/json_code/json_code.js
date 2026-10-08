import { Component, t, useProps, usePlugin } from '@odoo/owl';

import { CodeEditor } from '@web/core/code_editor/code_editor';
import { _t } from '@web/core/l10n/translation';
import { NotificationPlugin } from '@web/core/notifications/notification_plugin';
import { registry } from '@web/core/registry';
import { useBus } from '@web/core/utils/hooks';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const LINE_HEIGHT = 13;
const VERTICAL_PAD = 4;

/** JSON field edited as code, parsed and validated when it is committed. */
export class JsonCodeField extends Component {
    static template = 'muk_ai.JsonCodeField';
    static components = { CodeEditor };
    props = useProps({
        ...standardFieldProps,
        mode: t.string().optional('javascript'),
    });
    notification = usePlugin(NotificationPlugin);
    setup() {
        this.edited = null;
        const bus = this.props.record.model.bus;
        useBus(bus, 'WILL_SAVE_URGENTLY', () => this.commit());
        useBus(bus, 'NEED_LOCAL_CHANGES', ({ detail }) =>
            detail.proms.push(this.commit()),
        );
    }
    get text() {
        const value = this.props.record.data[this.props.name];
        return value === null || value === undefined || value === false
            ? ''
            : JSON.stringify(value, null, 2);
    }
    get style() {
        const lines = this.text.split('\n').length;
        return this.props.readonly
            ? `--mk-json-code-height: ${lines * LINE_HEIGHT + VERTICAL_PAD * 2}px;`
            : '';
    }
    onChange(text) {
        this.edited = text === this.text ? null : text;
        this.props.record.model.bus.trigger('FIELD_IS_DIRTY', this.edited !== null);
    }
    /**
     * Parse what was typed into the record, or flag the field invalid.
     */
    async commit() {
        if (this.props.readonly || this.edited === null) {
            return;
        }
        const { record, name } = this.props;
        let value;
        try {
            value = this.edited.trim() ? JSON.parse(this.edited) : false;
        } catch (error) {
            this.notification.add(
                _t('Invalid JSON in %(field)s: %(error)s', {
                    field: record.fields[name].string,
                    error: error.message,
                }),
                { type: 'danger', sticky: true },
            );
            return record.setInvalidField(name);
        }
        this.edited = null;
        await record.resetFieldValidity(name);
        await record.update({ [name]: value });
        record.model.bus.trigger('FIELD_IS_DIRTY', false);
    }
}

registry.category('fields').add('json_code', {
    component: JsonCodeField,
    displayName: _t('JSON Code Editor'),
    supportedOptions: [{ label: _t('Mode'), name: 'mode', type: 'string' }],
    supportedTypes: ['json'],
    extractProps: ({ options }) => ({ mode: options.mode || 'javascript' }),
});
