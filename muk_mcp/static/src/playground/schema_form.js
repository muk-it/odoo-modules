import { Component } from '@odoo/owl';
import { detectSchemaKind } from './utils';

/**
 * Renders an editable form for an object JSON schema, dispatching each property to
 * the appropriate widget (string, int, number, bool, enum, or raw JSON).
 */
export class SchemaForm extends Component {
    static template = 'muk_mcp.SchemaForm';
    static props = {
        schema: Object,
        value: Object,
        onChange: Function,
    };
    /**
     * Flatten the object schema's properties into renderable field descriptors.
     * @returns {object[]} fields with `name`, `schema`, `required`, and `kind`
     */
    get fields() {
        const schema = this.props.schema || {};
        if (schema.type !== 'object') {
            return [];
        }
        const props = schema.properties || {};
        const required = new Set(schema.required || []);
        return Object.entries(props).map(([name, sub]) => ({
            name,
            schema: sub,
            required: required.has(name),
            kind: detectSchemaKind(sub),
        }));
    }
    getValue(name) {
        return this.props.value ? this.props.value[name] : undefined;
    }
    /**
     * Update one field on an immutable copy of the value and emit it via onChange.
     * Empty or undefined values delete the key rather than storing it.
     * @param {string} name field name to update
     * @param {*} newValue new value, or '' / undefined to remove the field
     */
    setValue(name, newValue) {
        const next = { ...(this.props.value || {}) };
        if (newValue === undefined || newValue === '') {
            delete next[name];
        } else {
            next[name] = newValue;
        }
        this.props.onChange(next);
    }
    onStringChange(name, ev) {
        this.setValue(name, ev.target.value);
    }
    onIntChange(name, ev) {
        const v = ev.target.value;
        this.setValue(name, v === '' ? undefined : parseInt(v, 10));
    }
    onNumberChange(name, ev) {
        const v = ev.target.value;
        this.setValue(name, v === '' ? undefined : parseFloat(v));
    }
    onBoolChange(name, ev) {
        this.setValue(name, ev.target.checked);
    }
    onSelectChange(name, ev) {
        this.setValue(name, ev.target.value || undefined);
    }
    /**
     * Parse a raw-JSON field input, setting the value or surfacing a validity error.
     * Blank input clears the field; invalid JSON triggers native form validation.
     * @param {string} name field name
     * @param {Event} ev input event whose target carries the JSON text
     */
    onJsonChange(name, ev) {
        const text = ev.target.value;
        if (!text.trim()) {
            this.setValue(name, undefined);
            return;
        }
        try {
            this.setValue(name, JSON.parse(text));
            ev.target.setCustomValidity('');
        } catch (err) {
            ev.target.setCustomValidity(err.message);
            ev.target.reportValidity();
        }
    }
    /**
     * Serialize a field value to indented JSON for the raw-JSON textarea.
     * @param {string} name field name
     * @returns {string} pretty-printed JSON, or '' when the value is null/undefined
     */
    jsonText(name) {
        const val = this.getValue(name);
        if (val === undefined || val === null) {
            return '';
        }
        try {
            return JSON.stringify(val, null, 2);
        } catch {
            return String(val);
        }
    }
}
