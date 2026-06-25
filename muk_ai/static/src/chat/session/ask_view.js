/**
 * Serialize an ask/approval block's preview arguments to pretty JSON.
 * @param {object} block ask/approval block
 * @returns {string} pretty-printed JSON, or a string fallback
 */
export function askArgsText(block) {
    const raw = block?.preview?.arguments || block?.preview || {};
    try {
        return JSON.stringify(raw, null, 2);
    } catch {
        return String(raw);
    }
}

/**
 * Resolve the display mode (human/technical) for an ask block.
 * @param {object} block ask/approval block
 * @param {object} overrides per-call mode overrides keyed by callId
 * @returns {string} 'human' or 'technical'
 */
export function askViewMode(block, overrides) {
    const override = overrides && block ? overrides[block.callId] : null;
    if (override) {
        return override;
    }
    return block?.preview?.kind ? 'human' : 'technical';
}

/**
 * Return the opposite display mode for an ask block.
 * @param {object} block ask/approval block
 * @param {object} overrides per-call mode overrides keyed by callId
 * @returns {string} the toggled mode
 */
export function toggleAskViewMode(block, overrides) {
    const current = askViewMode(block, overrides);
    return current === 'human' ? 'technical' : 'human';
}
