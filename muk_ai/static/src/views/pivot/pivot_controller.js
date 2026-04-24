import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { PivotController } from '@web/views/pivot/pivot_controller';

import { makePivotContextDispatch } from '@muk_ai/views/context';

patch(PivotController.prototype, {
    setup() {
        super.setup(...arguments);
        if (!this.env.services['muk_ai.chat_window']) {
            return;
        }
        const dispatch = makePivotContextDispatch(this);
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
