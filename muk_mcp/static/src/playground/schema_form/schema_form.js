import { Component, t, useProps } from '@odoo/owl';

const KINDS = { boolean: 'bool', integer: 'int', number: 'number', string: 'string' };
const PARSERS = { int: (v) => parseInt(v, 10), number: parseFloat };

/**
 * Editable form for an object JSON schema, rendering each property with the input
 * matching its type and raw JSON for anything structured.
 */
export class SchemaForm extends Component {
    static template = 'muk_mcp.SchemaForm';
    props = useProps({
        schema: t.object(),
        value: t.object(),
        onChange: t.function(),
    });
    /**
     * Describe the properties of the schema as form fields.
     * @returns {object[]} fields with `name`, `schema`, `required` and `kind`
     */
    get fields() {
        const required = new Set(this.props.schema.required || []);
        return Object.entries(this.props.schema.properties || {}).map(
            ([name, schema]) => {
                const type = [schema.type].flat()[0];
                return {
                    name,
                    schema,
                    required: required.has(name),
                    kind: schema.enum ? 'enum' : KINDS[type] || 'json',
                };
            },
        );
    }
    /**
     * Emit the value with one field replaced, an empty input removing the field.
     * @param {string} name field name
     * @param {*} value new value, '' or undefined to remove the field
     */
    setValue(name, value) {
        const next = { ...this.props.value, [name]: value };
        if (value === undefined || value === '') {
            delete next[name];
        }
        this.props.onChange(next);
    }
    /**
     * Read an input event into the value of its field.
     * @param {object} field field descriptor from `fields`
     * @param {Event} ev input or change event
     */
    onInput(field, ev) {
        const { checked, value } = ev.target;
        if (field.kind === 'bool') {
            this.setValue(field.name, checked);
        } else if (field.kind in PARSERS) {
            this.setValue(field.name, value ? PARSERS[field.kind](value) : undefined);
        } else if (field.kind === 'json') {
            this.onJsonInput(field.name, ev.target);
        } else {
            this.setValue(field.name, value);
        }
    }
    /**
     * Parse a raw JSON input, flagging invalid JSON on the input itself.
     * @param {string} name field name
     * @param {HTMLTextAreaElement} input the edited textarea
     */
    onJsonInput(name, input) {
        try {
            this.setValue(
                name,
                input.value.trim() ? JSON.parse(input.value) : undefined,
            );
            input.setCustomValidity('');
        } catch (error) {
            input.setCustomValidity(error.message);
            input.reportValidity();
        }
    }
    /**
     * Render the value of a structured field as indented JSON.
     * @param {string} name field name
     * @returns {string} the indented JSON, or '' when the field is unset
     */
    jsonText(name) {
        const value = this.props.value[name];
        return value === undefined || value === null
            ? ''
            : JSON.stringify(value, null, 2);
    }
}
