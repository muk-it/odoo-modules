import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { GraphController } from '@web/views/graph/graph_controller';

import { useAdjustTarget } from '@muk_ai/views/adjust';
import { makeGraphContextDispatch } from '@muk_ai/views/context';

/** Capture the active graph view as AI view context for open chat windows. */
patch(GraphController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        useAdjustTarget(this);
        const dispatch = makeGraphContextDispatch(this);
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
