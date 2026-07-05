import { reactive } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { makeContext } from '@web/core/context';
import { session } from '@web/session';

import { ActionMenus } from '@web/search/action_menus/action_menus';

/** Run batch-flagged actions chunk by chunk with a blocking progress bar. */
patch(ActionMenus.prototype, {
    setup() {
        super.setup(...arguments);
        this.uiService = useService('ui');
        this.blockProgressService = useService('block_progress');
    },
    /**
     * Execute a batch action by resolving the active ids, slicing them into
     * batches, and dispatching one action call per batch while reporting
     * progress. Falls back to the default behaviour for non-batch actions.
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
        const totalBatches = Math.ceil(activeIds.length / batchSize);
        const importProgress = reactive({
            step: 0,
            value: 0,
        });
        this.uiService.block();
        this.blockProgressService.block({
            totalSteps: totalBatches,
            progressData: importProgress,
        });
        try {
            for (let i = 0; i < activeIds.length; i += batchSize) {
                const batchIds = activeIds.slice(i, i + batchSize);
                const activeIdsContext = {
                    active_id: batchIds[0],
                    active_ids: batchIds,
                    active_model: this.props.resModel,
                };
                if (this.props.domain) {
                    activeIdsContext.active_domain = this.props.domain;
                }
                const context = makeContext([this.props.context, activeIdsContext]);
                await this.actionService.doAction(action.id, {
                    additionalContext: context,
                    onClose: this.props.onActionExecuted,
                });
                importProgress.step = Math.floor(i / batchSize) + 1;
                importProgress.value = Math.round(
                    (importProgress.step / totalBatches) * 100,
                );
                if (i + batchSize < activeIds.length) {
                    const delay = session.test_mode ? 0 : 5400;
                    await new Promise((resolve) => setTimeout(resolve, delay));
                }
            }
        } finally {
            this.uiService.unblock();
            this.blockProgressService.unblock();
        }
    },
});
