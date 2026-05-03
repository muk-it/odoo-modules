/** @odoo-module */

function safeClone(value) {
    try {
        return JSON.parse(JSON.stringify(value));
    } catch {
        return value;
    }
}

export function schemaDefault(schema) {
    if (!schema || typeof schema !== "object") {
        return undefined;
    }
    if (schema.default !== undefined) {
        return safeClone(schema.default);
    }
    if (Array.isArray(schema.enum) && schema.enum.length) {
        return schema.enum[0];
    }
    const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
    switch (type) {
        case "object":
            return {};
        case "array":
            return [];
        case "boolean":
            return false;
        case "integer":
        case "number":
            return null;
        case "string":
            return "";
        default:
            return undefined;
    }
}

export function buildInitialValue(schema) {
    if (!schema || schema.type !== "object") {
        return schemaDefault(schema);
    }
    const out = {};
    const props = schema.properties || {};
    const required = new Set(schema.required || []);
    for (const [key, sub] of Object.entries(props)) {
        if (sub.default !== undefined || required.has(key)) {
            const val = schemaDefault(sub);
            if (val !== undefined) {
                out[key] = val;
            }
        }
    }
    return out;
}

export function cleanValue(value) {
    if (Array.isArray(value)) {
        return value.map(cleanValue).filter((v) => v !== undefined);
    }
    if (value && typeof value === "object") {
        const out = {};
        for (const [k, v] of Object.entries(value)) {
            const cleaned = cleanValue(v);
            if (cleaned !== undefined && cleaned !== "" && cleaned !== null) {
                out[k] = cleaned;
            }
        }
        return out;
    }
    return value;
}

export function buildCurl({ baseUrl, key, toolName, args }) {
    const body = {
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: { name: toolName, arguments: args || {} },
    };
    const auth = key ? ` \\\n  -H 'Authorization: Bearer ${key}'` : "";
    return [
        `curl -X POST '${baseUrl}/mcp'${auth} \\`,
        `  -H 'Content-Type: application/json' \\`,
        `  -H 'Accept: application/json' \\`,
        `  -d '${JSON.stringify(body)}'`,
    ].join("\n");
}

export function buildJsonRpc(toolName, args) {
    return JSON.stringify(
        {
            jsonrpc: "2.0",
            id: 1,
            method: "tools/call",
            params: { name: toolName, arguments: args || {} },
        },
        null,
        2
    );
}

export function prettyJson(text) {
    if (!text) {
        return "";
    }
    try {
        return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
        return text;
    }
}

export function parseToolResult(body) {
    if (!body) {
        return { kind: "empty", text: "", blocks: [] };
    }
    if (body.error) {
        return {
            kind: "error",
            code: body.error.code,
            message: body.error.message,
            blocks: [],
        };
    }
    const result = body.result;
    if (!result) {
        return { kind: "empty", text: "", blocks: [] };
    }
    const blocks = result.content || [];
    const text = blocks
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("\n");
    return {
        kind: result.isError ? "tool_error" : "ok",
        text,
        blocks,
    };
}

export function detectSchemaKind(schema) {
    if (!schema) {
        return "json";
    }
    if (Array.isArray(schema.enum)) {
        return "enum";
    }
    const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
    if (type === "boolean") {
        return "bool";
    }
    if (type === "integer") {
        return "int";
    }
    if (type === "number") {
        return "number";
    }
    if (type === "string") {
        return "string";
    }
    return "json";
}

export function categoryLabel(category) {
    const map = { read: "Read", write: "Write", other: "Other" };
    return map[category] || category;
}

export function categoryBadge(category) {
    const map = { read: "text-bg-info", write: "text-bg-warning" };
    return map[category] || "text-bg-secondary";
}

export function groupTools(tools) {
    const groups = new Map();
    for (const tool of tools) {
        const g = tool.category || "other";
        if (!groups.has(g)) {
            groups.set(g, []);
        }
        groups.get(g).push(tool);
    }
    for (const list of groups.values()) {
        list.sort((a, b) => a.name.localeCompare(b.name));
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}
