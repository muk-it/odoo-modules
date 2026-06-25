import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { FormController } from '@web/views/form/form_controller';

import { captureViewContext } from '@muk_ai/views/context';

/** Capture the open record/list as AI view context for active chat windows. */
patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        const chatWindow = this.env.services['muk_ai.chat_window'];
        if (!chatWindow) {
            return;
        }
        let lastKey = null;
        const dispatch = () => {
            try {
                const sessionIds = chatWindow.sessionIds || [];
                if (!sessionIds.length) {
                    lastKey = null;
                    return;
                }
                const root = this.model?.root;
                if (!root || !root.resModel) {
                    return;
                }
                let payload;
                if (root.resId) {
                    const data = root.data || {};
                    const displayName = data.display_name || data.name || '';
                    payload = {
                        kind: 'record',
                        model: root.resModel,
                        id: root.resId,
                        display_name: String(displayName || ''),
                    };
                } else {
                    payload = {
                        kind: 'list',
                        model: root.resModel,
                        view_type: 'form',
                    };
                }
                const key = `${sessionIds.join(',')}:${JSON.stringify(payload)}`;
                if (key === lastKey) {
                    return;
                }
                lastKey = key;
                captureViewContext(this.env, payload);
            } catch {
                /* ignore */
            }
        };
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
