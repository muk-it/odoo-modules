import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { KanbanController } from '@web/views/kanban/kanban_controller';

import { makeListContextDispatch } from '@muk_ai/views/context';

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        const dispatch = makeListContextDispatch(this, 'kanban');
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
