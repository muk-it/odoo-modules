import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { ListController } from '@web/views/list/list_controller';

import { useAdjustTarget } from '@muk_ai/views/adjust';
import { makeListContextDispatch } from '@muk_ai/views/context';

/** Capture the active list view as AI view context for open chat windows. */
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        useAdjustTarget(this);
        const dispatch = makeListContextDispatch(this, 'list');
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
