import { describe, expect, test } from '@odoo/hoot';
import { advanceTime } from '@odoo/hoot-mock';
import { session } from '@web/session';
import { registry } from '@web/core/registry';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import { getAutoLoadInterval } from '@muk_web_refresh/core/utils';
import {
    REFRESH_VIEW_EVENT,
    refreshService,
} from '@muk_web_refresh/services/refresh_service';

describe.current.tags('muk_web_refresh');

/**
 * Start the refresh service against stubbed dependencies.
 * @param {object} controller the value returned by ``action.currentController``
 * @returns {object} the captured bus notify callback, event log and start flag
 */
function startService(controller) {
    const events = [];
    let notify = null;
    let started = false;
    const env = {
        bus: {
            trigger(name) {
                events.push(name);
            },
        },
    };
    refreshService.start(env, {
        bus_service: {
            subscribe(channel, callback) {
                expect(channel).toBe('muk_web_refresh.reload');
                notify = callback;
            },
            start() {
                started = true;
            },
        },
        action: {
            get currentController() {
                return controller;
            },
        },
    });
    return {
        events,
        started,
        notify: (payload) => notify(payload),
    };
}

/**
 * Build an act_window controller descriptor.
 * @param {string} resModel the model of the current action
 * @param {string} viewType the current view type
 * @param {number} [resId] the currently displayed record id
 * @returns {object} the controller descriptor
 */
function makeController(resModel, viewType, resId) {
    return {
        action: { type: 'ir.actions.act_window', res_model: resModel },
        view: { type: viewType },
        currentState: { resId },
    };
}

test('the service is registered and starts the bus', async () => {
    expect(registry.category('services').get('muk_web_refresh.reload')).toBe(
        refreshService,
    );
    expect(refreshService.dependencies).toEqual(['bus_service', 'action']);
    expect(startService(makeController('res.partner', 'list')).started).toBe(true);
});

test('a matching notification triggers a view refresh', async () => {
    const svc = startService(makeController('res.partner', 'list'));
    svc.notify({ model: 'res.partner', view_types: [], rec_ids: [] });
    expect(svc.events).toEqual([REFRESH_VIEW_EVENT]);
});

test('a notification for another model is ignored', async () => {
    const svc = startService(makeController('res.partner', 'list'));
    svc.notify({ model: 'res.users', view_types: [], rec_ids: [] });
    expect(svc.events).toEqual([]);
});

test('a notification is ignored without an act_window controller', async () => {
    const svc = startService(null);
    svc.notify({ model: 'res.partner', view_types: [], rec_ids: [] });
    expect(svc.events).toEqual([]);
    const clientAction = startService({
        action: { type: 'ir.actions.client', res_model: 'res.partner' },
        view: { type: 'list' },
    });
    clientAction.notify({ model: 'res.partner', view_types: [], rec_ids: [] });
    expect(clientAction.events).toEqual([]);
});

test('view types restrict the refresh to the matching view', async () => {
    const list = startService(makeController('res.partner', 'list'));
    list.notify({ model: 'res.partner', view_types: ['kanban'] });
    expect(list.events).toEqual([]);
    const kanban = startService(makeController('res.partner', 'kanban'));
    kanban.notify({ model: 'res.partner', view_types: ['kanban'] });
    expect(kanban.events).toEqual([REFRESH_VIEW_EVENT]);
});

test('record ids restrict the refresh to the displayed record', async () => {
    const form = startService(makeController('res.partner', 'form', 5));
    form.notify({ model: 'res.partner', rec_ids: [7] });
    expect(form.events).toEqual([]);
    form.notify({ model: 'res.partner', rec_ids: [5, 7] });
    expect(form.events).toEqual([REFRESH_VIEW_EVENT]);
});

test('record ids are ignored on a view without a current record', async () => {
    const list = startService(makeController('res.partner', 'list'));
    list.notify({ model: 'res.partner', rec_ids: [7] });
    expect(list.events).toEqual([REFRESH_VIEW_EVENT]);
});

test('bursts are throttled to one refresh per third of the interval', async () => {
    const svc = startService(makeController('res.partner', 'list'));
    const payload = { model: 'res.partner', view_types: [], rec_ids: [] };
    svc.notify(payload);
    svc.notify(payload);
    svc.notify(payload);
    expect(svc.events).toHaveLength(1);
    await advanceTime(getAutoLoadInterval() / 3 + 100);
    expect(svc.events).toHaveLength(2);
    await advanceTime(getAutoLoadInterval());
    expect(svc.events).toHaveLength(2);
    svc.notify(payload);
    expect(svc.events).toHaveLength(3);
});

test('the throttle window follows the configured interval', async () => {
    patchWithCleanup(session, { pager_autoload_interval: 3000 });
    expect(getAutoLoadInterval()).toBe(3000);
    const svc = startService(makeController('res.partner', 'list'));
    const payload = { model: 'res.partner', view_types: [], rec_ids: [] };
    svc.notify(payload);
    svc.notify(payload);
    expect(svc.events).toHaveLength(1);
    await advanceTime(1100);
    expect(svc.events).toHaveLength(2);
});
