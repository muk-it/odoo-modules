import { rpcBus } from '@web/core/network/rpc';
import { UPDATE_METHODS } from '@web/core/orm_plugin';

/** Drop the cached views when a router changes, as its buttons are part of the Lost Emails list. */
rpcBus.addEventListener('RPC:RESPONSE', (ev) => {
    const { model, method } = ev.detail.data.params;
    if (
        model === 'muk_mail_route.configuration' &&
        !ev.detail.error &&
        UPDATE_METHODS.includes(method)
    ) {
        rpcBus.trigger('CLEAR-CACHES', 'get_views');
    }
});
