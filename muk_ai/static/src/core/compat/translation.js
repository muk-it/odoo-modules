// @odoo-module

import { _t as _translate } from '@web/core/l10n/translation';
import { sprintf } from '@web/core/utils/strings';

/**
 * Translate a term, interpolating any trailing values.
 *
 * Odoo 16's ``_t`` takes the term only; interpolation arrived in 17.0. This
 * keeps the later call style working by routing the extra arguments through
 * ``sprintf``, which supports both ``%s`` and ``%(name)s`` placeholders.
 *
 * @param {string} term source term to translate
 * @param {...any} values positional values, or a single object for named ones
 * @returns {string} the translated, interpolated string
 */
export function _t(term, ...values) {
    const translated = _translate(term);
    return values.length ? sprintf(translated, ...values) : translated;
}
