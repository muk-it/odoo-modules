import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { PivotController } from '@web/views/pivot/pivot_controller';

import { useAdjustTarget } from '@muk_ai/views/adjust';
import { makePivotContextDispatch } from '@muk_ai/views/context';

/** Capture the active pivot view as AI view context for open chat windows. */
patch(PivotController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        useAdjustTarget(this);
        const dispatch = makePivotContextDispatch(this);
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
