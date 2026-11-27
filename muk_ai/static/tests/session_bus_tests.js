// @odoo-module

import { Component, xml } from '@odoo/owl';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { makeFakeNotificationService } from '@web/../tests/helpers/mock_services';
import {
    getFixture,
    mount,
    nextTick,
    patchWithCleanup,
} from '@web/../tests/helpers/utils';

import { useAiSession } from '@muk_ai/chat/session/use_ai_session';

class Probe extends Component {
    static template = xml`<div/>`;
    static props = ['*'];
    setup() {
        this.session = useAiSession();
    }
}

/**
 * Mount a chat on session 7 whose server state `getState` reads.
 * @param {object} assert the QUnit assert, stepping each snapshot load
 * @param {function(): string} getState the state the server reports
 * @returns {Promise<object>} the session api
 */
async function openSession(assert, getState) {
    const services = registry.category('services');
    const fake = (name, value) =>
        services.add(name, { start: () => value }, { force: true });
    services.add('orm', ormService, { force: true });
    services.add('notification', makeFakeNotificationService(), { force: true });
    fake('bus_service', { addChannel() {}, deleteChannel() {}, subscribe() {} });
    fake('action', { doAction() {} });
    fake('dialog', { add() {} });
    fake('user', { userId: 1, context: {} });
    fake('muk_ai.session_notification', { markActive() {}, markInactive() {} });
    const env = await makeTestEnv({
        mockRPC(route, args) {
            if (args.method === 'get_snapshot') {
                assert.step('load');
                return { events: [] };
            }
            if (args.method === 'read') {
                return [{ id: 7, name: 'Chat', state: getState(), can_write: true }];
            }
        },
    });
    const probe = await mount(Probe, getFixture(), { env });
    await probe.session.load(7);
    return probe.session;
}

let runChecks;

/**
 * Run the pending running-state check and let the reload it starts settle.
 */
async function runCheck() {
    await runChecks[0].callback();
    await nextTick();
    await nextTick();
}

QUnit.module('session bus', {
    beforeEach() {
        runChecks = [];
        const { setTimeout, clearTimeout } = window;
        patchWithCleanup(window, {
            setTimeout(callback, delay) {
                if (delay !== 10000) {
                    return setTimeout(callback, delay);
                }
                const check = { callback };
                runChecks.push(check);
                return check;
            },
            clearTimeout(id) {
                if (runChecks.includes(id)) {
                    runChecks.splice(runChecks.indexOf(id), 1);
                } else {
                    clearTimeout(id);
                }
            },
        });
    },
});

QUnit.test(
    'a running chat on screen catches up with an end the bus never announced',
    async (assert) => {
        let state = 'running';
        const session = await openSession(assert, () => state);
        assert.verifySteps(['load']);
        await runCheck();
        assert.verifySteps([]);
        state = 'done';
        await runCheck();
        assert.verifySteps(['load']);
        assert.strictEqual(session.state.status, 'done');
        assert.strictEqual(runChecks.length, 0);
    },
);
