/** @odoo-module */

import { Component } from "@odoo/owl";
import { detectSchemaKind } from "./utils";

export class SchemaForm extends Component {
    static template = "muk_mcp.SchemaForm";
    static props = {
        schema: Object,
        value: Object,
        onChange: Function,
    };
    get fields() {
        const schema = this.props.schema || {};
        if (schema.type !== "object") {
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
    setValue(name, newValue) {
        const next = { ...(this.props.value || {}) };
        if (newValue === undefined || newValue === "") {
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
        this.setValue(name, v === "" ? undefined : parseInt(v, 10));
    }
    onNumberChange(name, ev) {
        const v = ev.target.value;
        this.setValue(name, v === "" ? undefined : parseFloat(v));
    }
    onBoolChange(name, ev) {
        this.setValue(name, ev.target.checked);
    }
    onSelectChange(name, ev) {
        this.setValue(name, ev.target.value || undefined);
    }
    onJsonChange(name, ev) {
        const text = ev.target.value;
        if (!text.trim()) {
            this.setValue(name, undefined);
            return;
        }
        try {
            this.setValue(name, JSON.parse(text));
            ev.target.setCustomValidity("");
        } catch (err) {
            ev.target.setCustomValidity(err.message);
            ev.target.reportValidity();
        }
    }
    jsonText(name) {
        const val = this.getValue(name);
        if (val === undefined || val === null) {
            return "";
        }
        try {
            return JSON.stringify(val, null, 2);
        } catch {
            return String(val);
        }
    }
}
