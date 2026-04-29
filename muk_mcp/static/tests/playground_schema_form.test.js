import { describe, expect, test } from "@odoo/hoot";

import { SchemaForm } from "@muk_mcp/playground/schema_form";

describe.current.tags("muk_mcp");

function makeForm(schema, value = {}) {
    const inst = Object.create(SchemaForm.prototype);
    inst.props = { schema, value, onChange: () => {} };
    return inst;
}

test("fields returns empty array for non-object schema", () => {
    expect(makeForm({ type: "string" }).fields).toEqual([]);
});

test("fields lists each property with its kind and required flag", () => {
    const inst = makeForm({
        type: "object",
        required: ["model"],
        properties: {
            model: { type: "string" },
            domain: { type: "array" },
            active_test: { type: "boolean" },
        },
    });
    const fields = inst.fields;
    expect(fields.length).toBe(3);
    const byName = Object.fromEntries(fields.map((f) => [f.name, f]));
    expect(byName.model.kind).toBe("string");
    expect(byName.model.required).toBe(true);
    expect(byName.domain.kind).toBe("json");
    expect(byName.domain.required).toBe(false);
    expect(byName.active_test.kind).toBe("bool");
});

test("getValue reads nested property from props.value", () => {
    const inst = makeForm({ type: "object", properties: {} }, { name: "Alice" });
    expect(inst.getValue("name")).toBe("Alice");
    expect(inst.getValue("missing")).toBe(undefined);
});

test("setValue emits the merged dict via onChange", () => {
    let captured = null;
    const inst = Object.create(SchemaForm.prototype);
    inst.props = {
        schema: { type: "object", properties: {} },
        value: { a: 1 },
        onChange: (next) => {
            captured = next;
        },
    };
    inst.setValue("b", 2);
    expect(captured).toEqual({ a: 1, b: 2 });
});

test("setValue removes keys when the new value is undefined or empty string", () => {
    let captured = null;
    const inst = Object.create(SchemaForm.prototype);
    inst.props = {
        schema: { type: "object", properties: {} },
        value: { a: 1, b: 2 },
        onChange: (next) => {
            captured = next;
        },
    };
    inst.setValue("a", "");
    expect(captured).toEqual({ b: 2 });
    inst.setValue("b", undefined);
    expect(captured).toEqual({ a: 1 });
});

test("jsonText stringifies complex values", () => {
    const inst = makeForm(
        { type: "object", properties: {} },
        { arr: [1, 2] }
    );
    expect(inst.jsonText("arr")).toBe("[\n  1,\n  2\n]");
});

test("jsonText returns empty string for undefined or null", () => {
    const inst = makeForm({ type: "object", properties: {} }, {});
    expect(inst.jsonText("missing")).toBe("");
});
