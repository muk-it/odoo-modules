import { reactive } from '@odoo/owl';
import { loadBundle } from '@web/core/assets';
import { registry } from '@web/core/registry';

import { seedSessionContext } from '@muk_ai/views/context';

export const DOCK_RIGHT = 16;
export const DOCK_WINDOW = 380;
export const DOCK_GAP = 10;

/**
 * Width the dock occupies with `count` windows open, excluding its own right
 * offset. Mirrors the geometry in chat_window.scss, and is shared with the
 * Discuss hub patch so both sides measure the dock the same way.
 * @param {number} count open chat windows
 * @returns {number} width in pixels, 0 when the dock is empty
 */
export function dockWidth(count) {
    return count ? count * DOCK_WINDOW + (count - 1) * DOCK_GAP : 0;
}

let prismPromise = null;
function ensurePrism() {
    if (!prismPromise) {
        prismPromise = loadBundle('html_editor.assets_prism').catch(() => {});
    }
    return prismPromise;
}

export const chatWindowService = {
    dependencies: ['action', 'bus_service', 'orm'],
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
        env.services.bus_service.subscribe('muk_ai.session_state', (payload) => {
            if (payload && payload.deleted && payload.session_id) {
                close(payload.session_id);
            }
        });
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
        function sessionIds() {
            return state.windows.map((w) => w.sessionId);
        }
        return {
            state,
            open,
            close,
            toggleMinimized,
            get activeSessionId() {
                return activeSessionId();
            },
            get sessionIds() {
                return sessionIds();
            },
        };
    },
};

registry.category('services').add('muk_ai.chat_window', chatWindowService);
