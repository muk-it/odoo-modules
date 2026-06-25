/**
 * Push a view-context payload to every open chat window's session.
 * @param {object} env component environment
 * @param {object} payload view context payload
 */
export function captureViewContext(env, payload) {
    const chatWindow = env.services?.['muk_ai.chat_window'];
    if (!chatWindow) {
        return;
    }
    const sessionIds = chatWindow.sessionIds || [];
    if (!sessionIds.length) {
        return;
    }
    if (!payload || !payload.model) {
        return;
    }
    const orm = env.services.orm;
    const caller = orm.silent || orm;
    for (const sessionId of sessionIds) {
        caller
            .call('muk_ai.session', 'set_view_context', [sessionId, payload])
            .catch(() => {});
    }
}

/**
 * Probe the current action controller and build its view-context payload.
 * @param {object} env component environment
 * @returns {Promise<object|null>} view context payload, or null when none
 */
export async function probeCurrentView(env) {
    try {
        const current = env.services?.action?.currentController;
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
                const rows = await caller.read(
                    resModel,
                    [props.resId],
                    ['display_name'],
                );
                displayName = rows?.[0]?.display_name || '';
            } catch {
                /* ignore */
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
    } catch {
        return null;
    }
}

/**
 * Seed a session's view context from an explicit payload or the current view.
 * @param {object} env component environment
 * @param {number} sessionId target session id
 * @param {object} [payload] explicit payload; probed when omitted
 * @returns {Promise<boolean>} whether the context was set
 */
export async function seedSessionContext(env, sessionId, payload = null) {
    if (!sessionId) {
        return false;
    }
    const ctx = payload || (await probeCurrentView(env));
    if (!ctx || !ctx.model) {
        return false;
    }
    const orm = env.services?.orm;
    if (!orm) {
        return false;
    }
    const caller = orm.silent || orm;
    try {
        await caller.call('muk_ai.session', 'set_view_context', [sessionId, ctx]);
        return true;
    } catch {
        return false;
    }
}

function makeDispatch(controller, build) {
    let lastKey = null;
    return () => {
        try {
            const chatWindow = controller.env.services['muk_ai.chat_window'];
            if (!chatWindow) {
                return;
            }
            const sessionIds = chatWindow.sessionIds || [];
            if (!sessionIds.length) {
                lastKey = null;
                return;
            }
            const payload = build(controller);
            if (!payload || !payload.model) {
                return;
            }
            const key = `${sessionIds.join(',')}:${JSON.stringify(payload)}`;
            if (key === lastKey) {
                return;
            }
            lastKey = key;
            captureViewContext(controller.env, payload);
        } catch {
            /* ignore */
        }
    };
}

/**
 * Build a dispatcher capturing list/kanban view context for a controller.
 * @param {object} controller the view controller
 * @param {string} viewType the list-family view type (e.g. 'list', 'kanban')
 * @returns {Function} a dedup-guarded dispatch callback
 */
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

/**
 * Build a dispatcher capturing pivot view context for a controller.
 * @param {object} controller the pivot controller
 * @returns {Function} a dedup-guarded dispatch callback
 */
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

/**
 * Build a dispatcher capturing graph view context for a controller.
 * @param {object} controller the graph controller
 * @returns {Function} a dedup-guarded dispatch callback
 */
export function makeGraphContextDispatch(controller) {
    return makeDispatch(controller, (ctrl) => {
        const meta = ctrl.model?.metaData;
        const resModel = meta?.resModel || ctrl.env.config?.resModel;
        if (!resModel) {
            return null;
        }
        const domain = ctrl.env.searchModel?.domain || [];
        const groupBys = (meta?.groupBy || [])
            .map((g) => g.fieldName || g)
            .filter(Boolean);
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
