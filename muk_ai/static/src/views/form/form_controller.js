/** @odoo-module */

import { onMounted, onPatched } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { FormController } from '@web/views/form/form_controller';

import { captureViewContext } from '../view_context_capture';

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
                if (!root || !root.resModel || !root.resId) {
                    return;
                }
                const key = `${sessionId}:${root.resModel}:${root.resId}`;
                if (key === lastKey) {
                    return;
                }
                lastKey = key;
                const data = root.data || {};
                const displayName = data.display_name || data.name || '';
                captureViewContext(this.env, {
                    kind: 'record',
                    model: root.resModel,
                    id: root.resId,
                    display_name: String(displayName || ''),
                });
            } catch (_e) {
                // Never let capture errors break form rendering.
            }
        };
        onMounted(dispatch);
        onPatched(dispatch);
    },
});
