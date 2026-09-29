import { _t } from '@web/core/l10n/translation';

/**
 * The read and edit modes offered by the switch, with a ``mode``, a
 * ``name`` and an ``icon`` each.
 */
export const LIST_MODES = [
    { mode: 'read', name: _t('Open Form View'), icon: 'open_in_new' },
    { mode: 'edit', name: _t('Inline Edit Mode'), icon: 'edit' },
];
