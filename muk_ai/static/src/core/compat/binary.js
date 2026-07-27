// @odoo-module

import { _t } from '@web/core/l10n/translation';
import { humanNumber } from '@web/core/utils/numbers';

/**
 * Render a byte count as a short human-readable size.
 *
 * Odoo 16 keeps this helper private inside ``@web/views/fields/formatters``;
 * ``@web/core/utils/binary`` only started exporting it in 17.0. The formatting
 * mirrors core so sizes read identically to the rest of the backend.
 *
 * @param {number} value size in bytes
 * @returns {string} the formatted size, or an empty string when falsy
 */
export function humanSize(value) {
    if (!value) {
        return '';
    }
    const suffix = value < 1024 ? ' ' + _t('Bytes') : 'b';
    return humanNumber(value, { decimals: 2 }) + suffix;
}
