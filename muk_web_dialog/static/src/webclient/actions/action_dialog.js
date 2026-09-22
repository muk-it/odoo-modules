import { patch } from '@web/core/utils/patch';
import { ActionDialog } from '@web/webclient/actions/action_dialog';

import '@mail/core/web/action_dialog_patch';

/** Hide the action dialog size toggle, the dialog header carries it. */
patch(ActionDialog.prototype, {
    get canExpand() {
        return false;
    },
});
