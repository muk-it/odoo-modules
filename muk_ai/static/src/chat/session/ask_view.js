export function askArgsText(block) {
    const raw = block?.preview?.arguments || block?.preview || {};
    try {
        return JSON.stringify(raw, null, 2);
    } catch (_e) {
        return String(raw);
    }
}

export function askViewMode(block, overrides) {
    const override = overrides && block ? overrides[block.callId] : null;
    if (override) {
        return override;
    }
    return block?.preview?.kind ? 'human' : 'technical';
}

export function toggleAskViewMode(block, overrides) {
    const current = askViewMode(block, overrides);
    return current === 'human' ? 'technical' : 'human';
}
