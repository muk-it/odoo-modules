import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { ListController } from '@web/views/list/list_controller';

import { makeListContextDispatch } from '@muk_ai/views/context';

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        const dispatch = makeListContextDispatch(this, 'list');
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
