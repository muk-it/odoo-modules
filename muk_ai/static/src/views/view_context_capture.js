/** @odoo-module */

export function captureViewContext(env, payload) {
    const chatWindow = env.services?.['muk_ai.chat_window'];
    if (!chatWindow) {
        return;
    }
    const sessionId = chatWindow.activeSessionId;
    if (!sessionId) {
        return;
    }
    if (!payload || !payload.model) {
        return;
    }
    const orm = env.services.orm;
    const caller = orm.silent || orm;
    caller
        .call('muk_ai.session', 'set_view_context', [sessionId, payload])
        .catch(() => {});
}

export function makeListContextDispatch(controller, viewType) {
    let lastKey = null;
    return () => {
        try {
            const chatWindow = controller.env.services['muk_ai.chat_window'];
            if (!chatWindow) {
                return;
            }
            const sessionId = chatWindow.activeSessionId;
            if (!sessionId) {
                lastKey = null;
                return;
            }
            const root = controller.model?.root;
            const resModel = root?.resModel || controller.env.config?.resModel;
            if (!resModel) {
                return;
            }
            const domain = controller.env.searchModel?.domain || [];
            const key = `${sessionId}:${resModel}:${viewType}:${JSON.stringify(domain)}`;
            if (key === lastKey) {
                return;
            }
            lastKey = key;
            const payload = {
                kind: 'list',
                model: resModel,
                view_type: viewType,
            };
            if (Array.isArray(domain) && domain.length) {
                payload.domain = domain;
            }
            captureViewContext(controller.env, payload);
        } catch (_e) {
            // Never let capture errors break view rendering.
        }
    };
}
