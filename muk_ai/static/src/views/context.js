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

function makeDispatch(controller, build) {
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
            const payload = build(controller);
            if (!payload || !payload.model) {
                return;
            }
            const key = `${sessionId}:${JSON.stringify(payload)}`;
            if (key === lastKey) {
                return;
            }
            lastKey = key;
            captureViewContext(controller.env, payload);
        } catch (_e) {}
    };
}

export function makeListContextDispatch(controller, viewType) {
    return makeDispatch(controller, (ctrl) => {
        const root = ctrl.model?.root;
        const resModel = root?.resModel || ctrl.env.config?.resModel;
        if (!resModel) {
            return null;
        }
        const domain = ctrl.env.searchModel?.domain || [];
        const payload = {
            kind: 'list',
            model: resModel,
            view_type: viewType,
        };
        if (Array.isArray(domain) && domain.length) {
            payload.domain = domain;
        }
        return payload;
    });
}

export function makePivotContextDispatch(controller) {
    return makeDispatch(controller, (ctrl) => {
        const meta = ctrl.model?.metaData;
        const resModel = meta?.resModel || ctrl.env.config?.resModel;
        if (!resModel) {
            return null;
        }
        const domain = ctrl.env.searchModel?.domain || [];
        const payload = {
            kind: 'pivot',
            model: resModel,
            view_type: 'pivot',
            pivot_measures: meta?.activeMeasures || [],
            pivot_row_groupby: meta?.fullRowGroupBys || [],
            pivot_column_groupby: meta?.fullColGroupBys || [],
        };
        if (Array.isArray(domain) && domain.length) {
            payload.domain = domain;
        }
        return payload;
    });
}

export function makeGraphContextDispatch(controller) {
    return makeDispatch(controller, (ctrl) => {
        const meta = ctrl.model?.metaData;
        const resModel = meta?.resModel || ctrl.env.config?.resModel;
        if (!resModel) {
            return null;
        }
        const domain = ctrl.env.searchModel?.domain || [];
        const groupBys = (meta?.groupBy || []).map((g) => g.fieldName || g).filter(Boolean);
        const payload = {
            kind: 'graph',
            model: resModel,
            view_type: 'graph',
            graph_mode: meta?.mode || 'bar',
            graph_measure: meta?.measure || '__count',
            graph_groupbys: groupBys,
        };
        if (meta?.order) {
            payload.graph_order = meta.order;
        }
        if (Array.isArray(domain) && domain.length) {
            payload.domain = domain;
        }
        return payload;
    });
}
