/** @odoo-module */

export function formatError(error) {
    return error?.data?.message || error?.message || String(error);
}
