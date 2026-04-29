import { describe, expect, test } from "@odoo/hoot";

import {
    buildCurl,
    buildInitialValue,
    buildJsonRpc,
    categoryBadge,
    categoryLabel,
    cleanValue,
    detectSchemaKind,
    groupTools,
    parseToolResult,
    prettyJson,
    schemaDefault,
} from "@muk_mcp/playground/utils";

describe.current.tags("muk_mcp");

// ----------------------------------------------------------
// schemaDefault
// ----------------------------------------------------------

test("schemaDefault honours explicit default", () => {
    expect(schemaDefault({ default: 42 })).toBe(42);
});

test("schemaDefault picks first enum entry when no default", () => {
    expect(schemaDefault({ enum: ["a", "b", "c"] })).toBe("a");
});

test("schemaDefault returns empty object for type object", () => {
    expect(schemaDefault({ type: "object" })).toEqual({});
});

test("schemaDefault returns empty array for type array", () => {
    expect(schemaDefault({ type: "array" })).toEqual([]);
});

test("schemaDefault returns false for boolean without default", () => {
    expect(schemaDefault({ type: "boolean" })).toBe(false);
});

// ----------------------------------------------------------
// buildInitialValue
// ----------------------------------------------------------

test("buildInitialValue fills required and default-bearing properties only", () => {
    const schema = {
        type: "object",
        required: ["model"],
        properties: {
            model: { type: "string" },
            domain: { type: "array", default: [] },
            fields: { type: "array" },
        },
    };
    expect(buildInitialValue(schema)).toEqual({
        model: "",
        domain: [],
    });
});

// ----------------------------------------------------------
// detectSchemaKind
// ----------------------------------------------------------

test("detectSchemaKind maps types to kinds", () => {
    expect(detectSchemaKind({ type: "boolean" })).toBe("bool");
    expect(detectSchemaKind({ type: "integer" })).toBe("int");
    expect(detectSchemaKind({ type: "number" })).toBe("number");
    expect(detectSchemaKind({ type: "string" })).toBe("string");
    expect(detectSchemaKind({ type: "object" })).toBe("json");
    expect(detectSchemaKind({ enum: ["a"] })).toBe("enum");
});

// ----------------------------------------------------------
// cleanValue
// ----------------------------------------------------------

test("cleanValue drops empty strings, nulls and undefined", () => {
    expect(
        cleanValue({ a: "", b: null, c: undefined, d: "x" })
    ).toEqual({ d: "x" });
});

test("cleanValue keeps 0 and false", () => {
    expect(cleanValue({ n: 0, b: false })).toEqual({ n: 0, b: false });
});

test("cleanValue walks arrays without dropping falsy values", () => {
    expect(cleanValue([1, "", null, undefined, 2])).toEqual([1, "", null, 2]);
});

test("cleanValue recurses into nested objects", () => {
    expect(
        cleanValue({ outer: { keep: 1, drop: "" } })
    ).toEqual({ outer: { keep: 1 } });
});

// ----------------------------------------------------------
// groupTools
// ----------------------------------------------------------

test("groupTools groups by category and sorts names", () => {
    const result = groupTools([
        { name: "zebra", category: "read" },
        { name: "apple", category: "read" },
        { name: "mango", category: "write" },
    ]);
    expect(result).toEqual([
        ["read", [{ name: "apple", category: "read" }, { name: "zebra", category: "read" }]],
        ["write", [{ name: "mango", category: "write" }]],
    ]);
});

// ----------------------------------------------------------
// parseToolResult
// ----------------------------------------------------------

test("parseToolResult classifies an ok result", () => {
    const parsed = parseToolResult({
        result: { content: [{ type: "text", text: "hello" }] },
    });
    expect(parsed.kind).toBe("ok");
    expect(parsed.text).toBe("hello");
});

test("parseToolResult classifies a tool-reported error", () => {
    const parsed = parseToolResult({
        result: {
            isError: true,
            content: [{ type: "text", text: "boom" }],
        },
    });
    expect(parsed.kind).toBe("tool_error");
});

test("parseToolResult classifies a JSON-RPC error envelope", () => {
    const parsed = parseToolResult({
        error: { code: -32603, message: "Internal" },
    });
    expect(parsed.kind).toBe("error");
    expect(parsed.code).toBe(-32603);
});

// ----------------------------------------------------------
// prettyJson
// ----------------------------------------------------------

test("prettyJson pretty-prints a JSON string", () => {
    expect(prettyJson('{"a":1}')).toBe('{\n  "a": 1\n}');
});

test("prettyJson returns original text on invalid JSON", () => {
    expect(prettyJson("not json")).toBe("not json");
});

// ----------------------------------------------------------
// buildCurl / buildJsonRpc
// ----------------------------------------------------------

test("buildCurl embeds the bearer token and tool arguments", () => {
    const curl = buildCurl({
        baseUrl: "https://example.odoo.com",
        key: "secret",
        toolName: "whoami",
        args: {},
    });
    expect(curl).toInclude("https://example.odoo.com/mcp");
    expect(curl).toInclude("Bearer secret");
    expect(curl).toInclude('"name":"whoami"');
});

test("buildJsonRpc produces a tools/call envelope", () => {
    const envelope = JSON.parse(buildJsonRpc("whoami", { a: 1 }));
    expect(envelope.method).toBe("tools/call");
    expect(envelope.params.name).toBe("whoami");
    expect(envelope.params.arguments).toEqual({ a: 1 });
});

// ----------------------------------------------------------
// categoryLabel / categoryBadge
// ----------------------------------------------------------

test("categoryLabel renders known categories and echoes unknown", () => {
    expect(categoryLabel("read")).toBe("Read");
    expect(categoryLabel("write")).toBe("Write");
    expect(categoryLabel("xyz")).toBe("xyz");
});

test("categoryBadge returns the correct Bootstrap class", () => {
    expect(categoryBadge("read")).toBe("text-bg-info");
    expect(categoryBadge("write")).toBe("text-bg-warning");
    expect(categoryBadge("other")).toBe("text-bg-secondary");
});
