import { reactive } from '@odoo/owl';
import { loadBundle } from '@web/core/assets';
import { registry } from '@web/core/registry';

import { seedSessionContext } from '@muk_ai/views/context';

let prismPromise = null;
function ensurePrism() {
    if (!prismPromise) {
        prismPromise = loadBundle('html_editor.assets_prism').catch(() => {});
    }
    return prismPromise;
}

export const chatWindowService = {
    dependencies: ['action', 'orm'],
    start(env) {
        const state = reactive({
            windows: [],
        });
        function find(id) {
            return state.windows.find((w) => w.sessionId === id);
        }
        function open(sessionId) {
            ensurePrism();
            const existing = find(sessionId);
            if (existing) {
                existing.minimized = false;
                return;
            }
            state.windows.push({ sessionId, minimized: false });
            seedSessionContext(env, sessionId);
        }
        function close(sessionId) {
            const idx = state.windows.findIndex((w) => w.sessionId === sessionId);
            if (idx >= 0) state.windows.splice(idx, 1);
        }
        function toggleMinimized(sessionId) {
            const entry = find(sessionId);
            if (entry) entry.minimized = !entry.minimized;
        }
        function activeSessionId() {
            for (let i = state.windows.length - 1; i >= 0; i--) {
                if (!state.windows[i].minimized) {
                    return state.windows[i].sessionId;
                }
            }
            return state.windows[0]?.sessionId || null;
        }
        return {
            state, open, close, toggleMinimized,
            get activeSessionId() { return activeSessionId(); },
        };
    },
};

registry.category('services').add('muk_ai.chat_window', chatWindowService);
