import { GlobalBusPlugin } from '@web/core/global_bus_plugin';
import { services } from '@web/core/services';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { BusPlugin } from '@bus/services/bus_plugin';

import { onWillDestroy, Plugin, usePlugin } from '@odoo/owl';

import { getAutoLoadInterval } from '@muk_web_refresh/core/utils/refresh';

export const REFRESH_VIEW_EVENT = 'muk_web_refresh.refresh-view';

/**
 * Tell whether the current view matches the reload notification payload.
 *
 * @param {object} action the action plugin driving the web client
 * @param {object} payload the bus notification payload
 * @returns {boolean} true when the open view should be reloaded
 */
export function shouldReload(action, payload) {
    const controller = action.currentController;
    if (!controller || controller.action.type !== 'ir.actions.act_window') {
        return false;
    }
    const { model, view_types, rec_ids } = payload;
    if (controller.action.res_model !== model) {
        return false;
    }
    if (view_types?.length && !view_types.includes(controller.view?.type)) {
        return false;
    }
    if (rec_ids?.length) {
        const currentResId = controller.currentState?.resId;
        if (currentResId && !rec_ids.includes(currentResId)) {
            return false;
        }
    }
    return true;
}

/**
 * Wrap a reload callback so it fires at most once per third of the interval.
 *
 * @param {Function} reloadFn the callback that reloads the current view
 * @returns {Function} a throttled version of the callback
 */
export function makeThrottledReload(reloadFn) {
    let lastReloadTime = 0;
    let pendingReload = null;
    return async () => {
        const now = Date.now();
        const elapsed = now - lastReloadTime;
        if (elapsed >= getAutoLoadInterval() / 3) {
            lastReloadTime = now;
            await reloadFn();
        } else if (!pendingReload) {
            pendingReload = setTimeout(
                async () => {
                    pendingReload = null;
                    lastReloadTime = Date.now();
                    await reloadFn();
                },
                getAutoLoadInterval() / 3 - elapsed,
            );
        }
    };
}

/** Turn reload notifications from the backend into view refreshes. */
export class RefreshPlugin extends Plugin {
    bus = usePlugin(BusPlugin);
    action = usePlugin(ActionPlugin);
    globalBus = usePlugin(GlobalBusPlugin);
    setup() {
        const throttledReload = makeThrottledReload(() =>
            this.globalBus.bus.trigger(REFRESH_VIEW_EVENT),
        );
        const unsubscribe = this.bus.subscribe('muk_web_refresh.reload', (payload) => {
            if (shouldReload(this.action, payload)) {
                throttledReload();
            }
        });
        this.bus.start();
        onWillDestroy(unsubscribe);
    }
}

services.add(RefreshPlugin);
