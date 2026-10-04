const CATEGORY_BADGES = { read: 'text-bg-info', write: 'text-bg-warning' };
const TYPE_DEFAULTS = {
    object: () => ({}),
    array: () => [],
    boolean: () => false,
    integer: () => null,
    number: () => null,
    string: () => '',
};

/**
 * Derive the value a JSON schema node starts from.
 * @param {object} schema JSON schema fragment
 * @returns {*} a copy of the explicit default, the first enum value, or the empty
 *   value of the node type
 */
function schemaDefault(schema) {
    if (schema.default !== undefined) {
        return structuredClone(schema.default);
    }
    if (schema.enum?.length) {
        return schema.enum[0];
    }
    const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
    return TYPE_DEFAULTS[type]?.();
}

/**
 * Build the initial arguments of an object schema from its required properties
 * and the properties that carry a default.
 * @param {object} schema JSON schema describing the arguments
 * @returns {object} the seeded arguments
 */
export function buildInitialValue(schema) {
    const required = new Set(schema.required || []);
    const value = {};
    for (const [key, sub] of Object.entries(schema.properties || {})) {
        if (sub.default !== undefined || required.has(key)) {
            const seed = schemaDefault(sub);
            if (seed !== undefined) {
                value[key] = seed;
            }
        }
    }
    return value;
}

/**
 * Recursively drop the empty members (undefined, '', null) of an object.
 * @param {*} value value to prune
 * @returns {*} the value without empty object members
 */
export function cleanValue(value) {
    if (Array.isArray(value)) {
        return value.map(cleanValue).filter((v) => v !== undefined);
    }
    if (value && typeof value === 'object') {
        const entries = Object.entries(value).map(([k, v]) => [k, cleanValue(v)]);
        return Object.fromEntries(
            entries.filter(([, v]) => v !== undefined && v !== '' && v !== null),
        );
    }
    return value;
}

/**
 * Indent a JSON string, returning any other text unchanged.
 * @param {string} text text that may hold JSON
 * @returns {string} the indented JSON or the original text
 */
export function prettyJson(text) {
    try {
        return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
        return text;
    }
}

/**
 * Group tools by category, both sorted by name.
 * @param {object[]} tools tool descriptors carrying `name` and `category`
 * @returns {Array} `[category, tools]` entries
 */
export function groupTools(tools) {
    const groups = Map.groupBy(tools, (tool) => tool.category || 'other');
    return [...groups.entries()]
        .map(([category, list]) => [
            category,
            list.toSorted((a, b) => a.name.localeCompare(b.name)),
        ])
        .sort(([a], [b]) => a.localeCompare(b));
}

/**
 * Resolve the badge class of a tool category.
 * @param {string} category category key
 * @returns {string} the badge class
 */
export function categoryBadge(category) {
    return CATEGORY_BADGES[category] || 'text-bg-secondary';
}

/**
 * Resolve the text class of an HTTP status.
 * @param {number} status HTTP status
 * @returns {string} the text class
 */
export function statusClass(status) {
    if (status >= 200 && status < 300) {
        return 'text-success';
    }
    return status >= 400 && status < 500 ? 'text-warning' : 'text-danger';
}
