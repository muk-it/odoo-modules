import { reactive } from '@odoo/owl';
import { loadBundle } from '@web/core/assets';
import { registry } from '@web/core/registry';

let prismPromise = null;
function ensurePrism() {
    if (!prismPromise) {
        prismPromise = loadBundle('html_editor.assets_prism').catch(() => {});
    }
    return prismPromise;
}

async function probeCurrentView(env) {
    try {
        const current = env.services.action?.currentController;
        if (!current) {
            return null;
        }
        const props = current.props || {};
        const resModel = props.resModel || current.action?.res_model;
        if (!resModel) {
            return null;
        }
        if (props.resId) {
            const orm = env.services.orm;
            const caller = orm.silent || orm;
            let displayName = '';
            try {
                const rows = await caller.read(resModel, [props.resId], ['display_name']);
                displayName = rows?.[0]?.display_name || '';
            } catch (_e) {
                // Fetch best-effort; empty display_name falls back to #id on the pill.
            }
            const payload = { kind: 'record', model: resModel, id: props.resId };
            if (displayName) {
                payload.display_name = displayName;
            }
            return payload;
        }
        const viewType = props.type || current.view?.type || 'list';
        const payload = { kind: 'list', model: resModel, view_type: viewType };
        const domain = props.domain || current.action?.domain;
        if (Array.isArray(domain) && domain.length) {
            payload.domain = domain;
        }
        return payload;
    } catch (_e) {
        return null;
    }
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
            (async () => {
                const payload = await probeCurrentView(env);
                if (!payload) {
                    return;
                }
                const orm = env.services.orm;
                const caller = orm.silent || orm;
                caller
                    .call('muk_ai.session', 'set_view_context',
                        [sessionId, payload])
                    .catch(() => {});
            })();
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
