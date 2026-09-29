import { proxy, usePlugin } from '@odoo/owl';

import { makeContext } from '@web/core/context';
import { UIPlugin } from '@web/core/ui/ui_plugin';
import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { session } from '@web/session';

import { ActionMenus } from '@web/search/action_menus/action_menus';

/** Run batch-flagged actions chunk by chunk with a blocking progress bar. */
patch(ActionMenus.prototype, {
    setup() {
        super.setup(...arguments);
        this.ui = usePlugin(UIPlugin);
        this.blockProgressService = useService('block_progress');
    },
    /**
     * Execute a batch action once per slice of the active ids, reporting the
     * progress after each slice. Other actions keep the default behaviour.
     * @param {object} action the action descriptor to execute
     * @returns {Promise<void>}
     */
    async executeAction(action) {
        if (!action.execute_in_batch) {
            return super.executeAction(...arguments);
        }
        let activeIds = this.props.getActiveIds();
        if (this.props.isDomainSelected) {
            activeIds = await this.orm.search(this.props.resModel, this.props.domain, {
                limit: session.active_ids_limit,
                context: this.props.context,
            });
        }
        const batchSize = action.execution_batch_size || 1;
        const totalSteps = Math.ceil(activeIds.length / batchSize);
        const progressData = proxy({ step: 0, value: 0 });
        this.ui.block();
        this.blockProgressService.block({ totalSteps, progressData });
        try {
            for (let step = 1; step <= totalSteps; step++) {
                const batchIds = activeIds.slice(
                    (step - 1) * batchSize,
                    step * batchSize,
                );
                const activeIdsContext = {
                    active_id: batchIds[0],
                    active_ids: batchIds,
                    active_model: this.props.resModel,
                };
                if (this.props.domain) {
                    activeIdsContext.active_domain = this.props.domain;
                }
                await this.actionService.doAction(action.id, {
                    additionalContext: makeContext([
                        this.props.context,
                        activeIdsContext,
                    ]),
                    onClose: this.props.onActionExecuted,
                });
                progressData.step = step;
                progressData.value = Math.round((step / totalSteps) * 100);
            }
        } finally {
            this.ui.unblock();
            this.blockProgressService.unblock();
        }
    },
});
