import { session } from '@web/session';
import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';
import { Dialog } from '@web/core/dialog/dialog';

import { signal } from '@odoo/owl';

/** Honor the user dialog size preference and add a maximize toggle. */
patch(Dialog.prototype, {
    setup() {
        super.setup();
        const maximized = signal(session.dialog_size === 'maximize');
        this.env.dialogData.mkSize = {
            maximized,
            canMaximize: () => !['sm', 'md'].includes(super.size),
            title: () => (maximized() ? _t('Compress') : _t('Expand')),
            toggle: () => maximized.set(!maximized()),
        };
    },
    get size() {
        const { canMaximize, maximized } = this.env.dialogData.mkSize;
        return canMaximize() && maximized() ? 'fs' : super.size;
    },
});
