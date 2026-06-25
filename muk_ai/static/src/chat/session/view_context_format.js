import { _t } from '@web/core/l10n/translation';

/**
 * Build a short label for a pinned view context.
 * @param {object} ctx view context payload
 * @returns {string} display label
 */
export function viewContextLabel(ctx) {
    if (!ctx) {
        return '';
    }
    if (ctx.kind === 'record') {
        const name = ctx.display_name || (ctx.id ? `#${ctx.id}` : '');
        return name ? `${ctx.model} · ${name}` : ctx.model;
    }
    if (ctx.kind === 'list') {
        return `${ctx.model} · ${ctx.view_type || 'list'}`;
    }
    if (ctx.kind === 'action') {
        return ctx.model || _t('Action');
    }
    return ctx.model || '';
}

/**
 * Build the multi-line tooltip for a pinned view context.
 * @param {object} ctx view context payload
 * @returns {string} tooltip text
 */
export function viewContextTooltip(ctx) {
    if (!ctx) {
        return '';
    }
    const parts = [viewContextLabel(ctx), _t('Click to open · /unpin to clear')];
    if (ctx.kind === 'list' && Array.isArray(ctx.domain) && ctx.domain.length) {
        parts.splice(1, 0, JSON.stringify(ctx.domain));
    }
    return parts.filter(Boolean).join('\n');
}
