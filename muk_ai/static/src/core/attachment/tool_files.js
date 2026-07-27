const MAX_RESULT_DEPTH = 4;

/**
 * Collect the files a tool result stored, into `out`.
 *
 * A file-producing tool answers with `attachment_id`, and the result reaches
 * the client either as a JSON string or nested inside a `tool_load` wrapper,
 * so the payload is walked rather than read at a fixed key.
 * @param {*} value tool result, at any nesting level
 * @param {Array} out collected attachment descriptors
 * @param {Set} seen dedup keys already emitted
 * @param {number} [depth] current recursion depth
 */
export function collectToolFiles(value, out, seen, depth = 0) {
    if (!value || depth > MAX_RESULT_DEPTH) {
        return;
    }
    if (typeof value === 'string') {
        if (!value.includes('attachment_id')) {
            return;
        }
        try {
            collectToolFiles(JSON.parse(value), out, seen, depth + 1);
        } catch {
            return;
        }
        return;
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            collectToolFiles(item, out, seen, depth + 1);
        }
        return;
    }
    if (typeof value !== 'object') {
        return;
    }
    const id = value.attachment_id;
    if (Number.isInteger(id) && !seen.has(`id:${id}`)) {
        seen.add(`id:${id}`);
        out.push({
            id,
            filename: value.filename || 'download',
            mimetype: value.mimetype || '',
        });
    }
    for (const nested of Object.values(value)) {
        collectToolFiles(nested, out, seen, depth + 1);
    }
}

/**
 * Return the files a single tool result stored.
 * @param {*} result tool result payload
 * @returns {Array<object>} attachment descriptors
 */
export function toolResultFiles(result) {
    const out = [];
    collectToolFiles(result, out, new Set());
    return out;
}
