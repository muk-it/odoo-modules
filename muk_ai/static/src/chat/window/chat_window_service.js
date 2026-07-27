// @odoo-module

import { reactive } from '@odoo/owl';
import { registry } from '@web/core/registry';

import { busSubscribe } from '@muk_ai/core/compat/bus';
import { seedSessionContext } from '@muk_ai/views/context';

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
        busSubscribe(env.services.bus_service, 'muk_ai.session_state', (payload) => {
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
