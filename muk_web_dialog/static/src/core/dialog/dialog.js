import { session } from '@web/session';
import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';
import { Dialog } from '@web/core/dialog/dialog';

import { signal } from '@odoo/owl';

const MINIMAL_SIZES = ['sm', 'md'];

/** Honor the user dialog size preference and add a maximize toggle. */
patch(Dialog.prototype, {
    setup() {
        super.setup();
        const maximized = signal(session.dialog_size === 'maximize');
        this.env.dialogData.mkSize = {
            maximized,
            canMaximize: () => !MINIMAL_SIZES.includes(this.requestedSize),
            title: () => (maximized() ? _t('Compress') : _t('Expand')),
            toggle: () => maximized.set(!maximized()),
        };
    },
    get requestedSize() {
        return super.size;
    },
    get size() {
        const { canMaximize, maximized } = this.env.dialogData.mkSize;
        return canMaximize() && maximized() ? 'fs' : super.size;
    },
});
