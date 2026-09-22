import { expect, test } from '@odoo/hoot';
import { advanceTime } from '@odoo/hoot-mock';

import { GlobalBusPlugin } from '@web/core/global_bus_plugin';
import { services } from '@web/core/services';
import { session } from '@web/session';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';
import {
    getService,
    makeTestApp,
    MockServer,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { startBusService } from '@bus/../tests/bus_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { getAutoLoadInterval } from '@muk_web_refresh/core/utils/refresh';
import {
    makeThrottledReload,
    RefreshPlugin,
    REFRESH_VIEW_EVENT,
    shouldReload,
} from '@muk_web_refresh/services/refresh/refresh_plugin';

defineMailModels();

function startService(controller) {
    const events = [];
    const action = {
        get currentController() {
            return controller;
        },
    };
    const reload = makeThrottledReload(() => events.push(REFRESH_VIEW_EVENT));
    return {
        events,
        notify: (payload) => {
            if (shouldReload(action, payload)) {
                reload();
            }
        },
    };
}

function makeController(resModel, viewType, resId) {
    return {
        action: { type: 'ir.actions.act_window', res_model: resModel },
        view: { type: viewType },
        currentState: { resId },
    };
}

test.tags('muk_web_refresh');
test('the plugin is registered as a service', async () => {
    expect(services.has(RefreshPlugin)).toBe(true);
});

test.tags('muk_web_refresh');
test('a matching notification triggers a view refresh', async () => {
    const svc = startService(makeController('res.partner', 'list'));
    svc.notify({ model: 'res.partner', view_types: [], rec_ids: [] });
    expect(svc.events).toEqual([REFRESH_VIEW_EVENT]);
});

test.tags('muk_web_refresh');
test('a notification for another model is ignored', async () => {
    const svc = startService(makeController('res.partner', 'list'));
    svc.notify({ model: 'res.users', view_types: [], rec_ids: [] });
    expect(svc.events).toEqual([]);
});

test.tags('muk_web_refresh');
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

test.tags('muk_web_refresh');
test('view types restrict the refresh to the matching view', async () => {
    const list = startService(makeController('res.partner', 'list'));
    list.notify({ model: 'res.partner', view_types: ['kanban'] });
    expect(list.events).toEqual([]);
    const kanban = startService(makeController('res.partner', 'kanban'));
    kanban.notify({ model: 'res.partner', view_types: ['kanban'] });
    expect(kanban.events).toEqual([REFRESH_VIEW_EVENT]);
});

test.tags('muk_web_refresh');
test('record ids restrict the refresh to the displayed record', async () => {
    const form = startService(makeController('res.partner', 'form', 5));
    form.notify({ model: 'res.partner', rec_ids: [7] });
    expect(form.events).toEqual([]);
    form.notify({ model: 'res.partner', rec_ids: [5, 7] });
    expect(form.events).toEqual([REFRESH_VIEW_EVENT]);
});

test.tags('muk_web_refresh');
test('record ids are ignored on a view without a current record', async () => {
    const list = startService(makeController('res.partner', 'list'));
    list.notify({ model: 'res.partner', rec_ids: [7] });
    expect(list.events).toEqual([REFRESH_VIEW_EVENT]);
});

test.tags('muk_web_refresh');
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

test.tags('muk_web_refresh');
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

test.tags('muk_web_refresh');
test('a bus notification reaches the global bus through the started plugin', async () => {
    await makeTestApp({ forceNew: true });
    Object.defineProperty(getService(ActionPlugin), 'currentController', {
        get: () => makeController('res.partner', 'list'),
        configurable: true,
    });
    startBusService();
    getService(GlobalBusPlugin).bus.addEventListener(REFRESH_VIEW_EVENT, () =>
        expect.step(REFRESH_VIEW_EVENT),
    );
    MockServer.env['bus.bus']._sendone('broadcast', 'muk_web_refresh.reload', {
        model: 'res.partner',
        view_types: [],
        rec_ids: [],
    });
    await expect.waitForSteps([REFRESH_VIEW_EVENT]);
});
