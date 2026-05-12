import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { FormController } from '@web/views/form/form_controller';

import { captureViewContext } from '@muk_ai/views/context';

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
                const sessionId = chatWindow.activeSessionId;
                if (!sessionId) {
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
                const key = `${sessionId}:${JSON.stringify(payload)}`;
                if (key === lastKey) {
                    return;
                }
                lastKey = key;
                captureViewContext(this.env, payload);
            } catch (_e) {}
        };
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
