import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { KanbanController } from '@web/views/kanban/kanban_controller';

import { useAdjustTarget } from '@muk_ai/views/adjust';
import { makeListContextDispatch } from '@muk_ai/views/context';

/** Capture the active kanban view as AI view context for open chat windows. */
patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        useAdjustTarget(this);
        const dispatch = makeListContextDispatch(this, 'kanban');
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
