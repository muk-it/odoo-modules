/**
 * Deep-clone a JSON-serializable value, falling back to the original on failure.
 * @param {*} value value to clone
 * @returns {*} a structural copy, or the input itself if it cannot be serialized
 */
function safeClone(value) {
    try {
        return JSON.parse(JSON.stringify(value));
    } catch {
        return value;
    }
}

/**
 * Derive a sensible default value for a JSON schema node.
 * @param {object} schema JSON schema fragment
 * @returns {*} the explicit default, first enum value, or a per-type empty value
 */
export function schemaDefault(schema) {
    if (!schema || typeof schema !== 'object') {
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
        case 'object':
            return {};
        case 'array':
            return [];
        case 'boolean':
            return false;
        case 'integer':
        case 'number':
            return null;
        case 'string':
            return '';
        default:
            return undefined;
    }
}

/**
 * Build the initial argument object for an object schema.
 * Seeds only properties that are required or carry an explicit default.
 * @param {object} schema JSON schema describing the tool arguments
 * @returns {*} an object pre-filled with seed values, or the scalar default for non-objects
 */
export function buildInitialValue(schema) {
    if (!schema || schema.type !== 'object') {
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

/**
 * Recursively strip empty entries (undefined, '', null) from a value.
 * @param {*} value value to prune
 * @returns {*} the value with empty object/array members removed
 */
export function cleanValue(value) {
    if (Array.isArray(value)) {
        return value.map(cleanValue).filter((v) => v !== undefined);
    }
    if (value && typeof value === 'object') {
        const out = {};
        for (const [k, v] of Object.entries(value)) {
            const cleaned = cleanValue(v);
            if (cleaned !== undefined && cleaned !== '' && cleaned !== null) {
                out[k] = cleaned;
            }
        }
        return out;
    }
    return value;
}

/**
 * Build a copy-pasteable curl command for a tools/call request.
 * @param {object} options
 * @param {string} options.baseUrl origin the /mcp endpoint is served from
 * @param {string} options.key MCP bearer key, omitted from the header when falsy
 * @param {string} options.toolName name of the tool to invoke
 * @param {object} options.args tool arguments
 * @returns {string} a multi-line curl command
 */
export function buildCurl({ baseUrl, key, toolName, args }) {
    const body = {
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: { name: toolName, arguments: args || {} },
    };
    const auth = key ? ` \\\n  -H 'Authorization: Bearer ${key}'` : '';
    return [
        `curl -X POST '${baseUrl}/mcp'${auth} \\`,
        `  -H 'Content-Type: application/json' \\`,
        `  -H 'Accept: application/json' \\`,
        `  -d '${JSON.stringify(body)}'`,
    ].join('\n');
}

/**
 * Build a pretty-printed JSON-RPC tools/call payload.
 * @param {string} toolName name of the tool to invoke
 * @param {object} args tool arguments
 * @returns {string} the indented JSON-RPC request body
 */
export function buildJsonRpc(toolName, args) {
    return JSON.stringify(
        {
            jsonrpc: '2.0',
            id: 1,
            method: 'tools/call',
            params: { name: toolName, arguments: args || {} },
        },
        null,
        2,
    );
}

/**
 * Pretty-print a JSON string, returning the input unchanged if it is not valid JSON.
 * @param {string} text raw text that may contain JSON
 * @returns {string} indented JSON, or the original text on parse failure
 */
export function prettyJson(text) {
    if (!text) {
        return '';
    }
    try {
        return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
        return text;
    }
}

/**
 * Normalize a JSON-RPC response body into a render-friendly result descriptor.
 * @param {object} body parsed JSON-RPC response, or a falsy value when absent
 * @returns {object} a descriptor with `kind` ('empty'|'error'|'tool_error'|'ok'),
 *   concatenated `text`, content `blocks`, and error `code`/`message` when applicable
 */
export function parseToolResult(body) {
    if (!body) {
        return { kind: 'empty', text: '', blocks: [] };
    }
    if (body.error) {
        return {
            kind: 'error',
            code: body.error.code,
            message: body.error.message,
            blocks: [],
        };
    }
    const result = body.result;
    if (!result) {
        return { kind: 'empty', text: '', blocks: [] };
    }
    const blocks = result.content || [];
    const text = blocks
        .filter((c) => c.type === 'text')
        .map((c) => c.text)
        .join('\n');
    return {
        kind: result.isError ? 'tool_error' : 'ok',
        text,
        blocks,
    };
}

/**
 * Map a JSON schema node to the form-widget kind that should render it.
 * @param {object} schema JSON schema fragment
 * @returns {string} one of 'enum', 'bool', 'int', 'number', 'string', or 'json'
 */
export function detectSchemaKind(schema) {
    if (!schema) {
        return 'json';
    }
    if (Array.isArray(schema.enum)) {
        return 'enum';
    }
    const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
    if (type === 'boolean') {
        return 'bool';
    }
    if (type === 'integer') {
        return 'int';
    }
    if (type === 'number') {
        return 'number';
    }
    if (type === 'string') {
        return 'string';
    }
    return 'json';
}

/**
 * Resolve the human-readable label for a tool category.
 * @param {string} category category key
 * @returns {string} the display label, or the key itself when unmapped
 */
export function categoryLabel(category) {
    const map = { read: 'Read', write: 'Write', other: 'Other' };
    return map[category] || category;
}

/**
 * Resolve the Bootstrap badge class for a tool category.
 * @param {string} category category key
 * @returns {string} the badge CSS class, defaulting to 'text-bg-secondary'
 */
export function categoryBadge(category) {
    const map = { read: 'text-bg-info', write: 'text-bg-warning' };
    return map[category] || 'text-bg-secondary';
}

/**
 * Group tools by category and sort each group by tool name.
 * @param {object[]} tools tool descriptors carrying `name` and optional `category`
 * @returns {Array} category-sorted entries of `[category, sortedTools]`
 */
export function groupTools(tools) {
    const groups = new Map();
    for (const tool of tools) {
        const g = tool.category || 'other';
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
