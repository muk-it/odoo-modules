import { patch } from '@web/core/utils/patch';
import { GraphController } from '@web/views/graph/graph_controller';
import { PivotController } from '@web/views/pivot/pivot_controller';

import {
    useViewContext,
    viewContextBuilders,
    withDomain,
} from '@muk_ai/views/view_context/view_context';

Object.assign(viewContextBuilders, {
    pivot(controller) {
        const meta = controller.model.metaData;
        return withDomain(
            {
                kind: 'pivot',
                model: meta.resModel,
                view_type: 'pivot',
                pivot_measures: meta.activeMeasures || [],
                pivot_row_groupby: meta.fullRowGroupBys || [],
                pivot_column_groupby: meta.fullColGroupBys || [],
            },
            controller,
        );
    },
    graph(controller) {
        const meta = controller.model.metaData;
        const payload = {
            kind: 'graph',
            model: meta.resModel,
            view_type: 'graph',
            graph_mode: meta.mode || 'bar',
            graph_measure: meta.measure || '__count',
            graph_groupbys: (meta.groupBy || []).map(
                (groupBy) => groupBy.fieldName || groupBy,
            ),
        };
        if (meta.order) {
            payload.graph_order = meta.order;
        }
        return withDomain(payload, controller);
    },
});

patch(PivotController.prototype, {
    setup() {
        super.setup(...arguments);
        useViewContext(this, 'pivot');
    },
});

patch(GraphController.prototype, {
    setup() {
        super.setup(...arguments);
        useViewContext(this, 'graph');
    },
});
