// @odoo-module

import { Component, xml } from '@odoo/owl';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { getFixture, mockTimeout, mount, nextTick } from '@web/../tests/helpers/utils';

import { useAiSession } from '@muk_ai/chat/session/use_ai_session';

class Probe extends Component {
    static template = xml`<div/>`;
    static props = ['*'];
    setup() {
        this.session = useAiSession();
    }
}

/**
 * Show a chat whose server state `getState` reads, and log each reload.
 * @param {object} assert the QUnit assert
 * @param {function(): string} getState the state the server answers
 * @returns {Promise<object>} the bus and the session api
 */
async function openSession(assert, getState) {
    const bus = Object.assign(new EventTarget(), {
        start() {},
        addChannel() {},
        deleteChannel() {},
    });
    const services = registry.category('services');
    const fake = (name, value) =>
        services.add(name, { start: () => value }, { force: true });
    services.add('orm', ormService, { force: true });
    fake('bus_service', bus);
    fake('user', { userId: 1, context: {} });
    fake('notification', { add() {} });
    fake('action', { currentController: null, doAction() {} });
    fake('dialog', { add() {} });
    fake('muk_ai.session_notification', { markActive() {}, markInactive() {} });
    const env = await makeTestEnv({
        mockRPC(route, args) {
            if (args.method === 'get_snapshot') {
                assert.step('load');
                return { id: 1, state: getState(), events: [] };
            }
            if (args.method === 'read') {
                return [{ id: 1, user_id: 1, can_write: true, state: getState() }];
            }
        },
    });
    const probe = await mount(Probe, getFixture(), { env });
    await probe.session.load(1);
    return { bus, session: probe.session };
}

QUnit.module('muk_ai', {}, function () {
    QUnit.module('session bus');

    QUnit.test(
        'a running chat on screen catches up with an end the bus never announced',
        async (assert) => {
            const { advanceTime } = mockTimeout();
            let state = 'running';
            const { session } = await openSession(assert, () => state);
            await advanceTime(10000);
            assert.verifySteps(['load']);
            state = 'done';
            await advanceTime(10000);
            assert.verifySteps(['load']);
            assert.strictEqual(session.state.status, 'done');
            await advanceTime(10000);
            assert.verifySteps([]);
        },
    );

    QUnit.test('a reconnected bus reloads the chat on screen', async (assert) => {
        const { bus } = await openSession(assert, () => 'done');
        assert.verifySteps(['load']);
        bus.dispatchEvent(new CustomEvent('reconnect'));
        await nextTick();
        assert.verifySteps(['load']);
    });
});
