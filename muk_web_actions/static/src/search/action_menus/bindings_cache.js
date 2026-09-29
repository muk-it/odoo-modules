import { rpcBus } from '@web/core/network/rpc';
import { UPDATE_METHODS } from '@web/core/orm_plugin';

const BATCH_MODELS = ['ir.actions.server', 'ir.actions.report'];

/**
 * Drop the cached view descriptions when a server action or a report is
 * changed, so the action menus pick up new batch settings on the next load.
 */
rpcBus.addEventListener('RPC:RESPONSE', (ev) => {
    const { model, method } = ev.detail.data.params;
    if (
        BATCH_MODELS.includes(model) &&
        UPDATE_METHODS.includes(method) &&
        !ev.detail.error
    ) {
        rpcBus.trigger('CLEAR-CACHES', 'get_views');
    }
});
