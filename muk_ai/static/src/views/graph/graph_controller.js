import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { GraphController } from '@web/views/graph/graph_controller';

import { makeGraphContextDispatch } from '@muk_ai/views/context';

patch(GraphController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        const dispatch = makeGraphContextDispatch(this);
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
