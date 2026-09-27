import { expect, test } from '@odoo/hoot';
import { advanceTime, animationFrame } from '@odoo/hoot-mock';

import { session } from '@web/session';
import {
    defineModels,
    fields,
    getService,
    models,
    MockServer,
    mountWebClient,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { startBusService } from '@bus/../tests/bus_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import {
    makeThrottledReload,
    shouldReload,
} from '@muk_web_refresh/services/refresh/refresh_plugin';

class Product extends models.Model {
    _records = [{ id: 1, name: 'Test 1' }];
    name = fields.Char();
}

defineModels([Product]);
defineMailModels();

function actionOn(type, resModel, viewType, resId) {
    return {
        currentController: {
            action: { type, res_model: resModel },
            view: { type: viewType },
            currentState: { resId },
        },
    };
}

test.tags('muk_web_refresh');
test('a reload notification from the server reloads the open list', async () => {
    onRpc('web_search_read', () => expect.step('reload'));
    await mountWebClient();
    await getService('action').doAction({
        type: 'ir.actions.act_window',
        res_model: 'product',
        views: [[false, 'list']],
    });
    await startBusService();
    expect.verifySteps(['reload']);
    MockServer.env['bus.bus']._sendone('broadcast', 'muk_web_refresh.reload', {
        model: 'res.partner',
        view_types: [],
        rec_ids: [],
    });
    await advanceTime(1000);
    await animationFrame();
    expect.verifySteps([]);
    MockServer.env['bus.bus']._sendone('broadcast', 'muk_web_refresh.reload', {
        model: 'product',
        view_types: ['list'],
        rec_ids: [],
    });
    await expect.waitForSteps(['reload']);
});

test.tags('muk_web_refresh');
test('a notification only reloads the view it targets', async () => {
    const list = actionOn('ir.actions.act_window', 'res.partner', 'list');
    const form = actionOn('ir.actions.act_window', 'res.partner', 'form', 5);
    const client = actionOn('ir.actions.client', 'res.partner', 'list');
    const cases = [
        [list, { model: 'res.partner', view_types: [], rec_ids: [] }, true],
        [list, { model: 'res.users', view_types: [], rec_ids: [] }, false],
        [{ currentController: null }, { model: 'res.partner' }, false],
        [client, { model: 'res.partner' }, false],
        [list, { model: 'res.partner', view_types: ['kanban'] }, false],
        [list, { model: 'res.partner', view_types: ['list', 'kanban'] }, true],
        [list, { model: 'res.partner', rec_ids: [7] }, true],
        [form, { model: 'res.partner', rec_ids: [7] }, false],
        [form, { model: 'res.partner', rec_ids: [5, 7] }, true],
    ];
    for (const [action, payload, expected] of cases) {
        expect(shouldReload(action, payload)).toBe(expected, {
            message: JSON.stringify(payload),
        });
    }
});

test.tags('muk_web_refresh');
test('bursts are throttled to one reload per third of the interval', async () => {
    patchWithCleanup(session, { pager_autoload_interval: 3000 });
    const reload = makeThrottledReload(() => expect.step('reload'));
    reload();
    reload();
    reload();
    expect.verifySteps(['reload']);
    await advanceTime(1100);
    expect.verifySteps(['reload']);
    await advanceTime(3000);
    expect.verifySteps([]);
    reload();
    expect.verifySteps(['reload']);
});
