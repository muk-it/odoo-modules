// @odoo-module

import { Component, xml } from '@odoo/owl';
import { browser } from '@web/core/browser/browser';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import {
    getFixture,
    mount,
    nextTick,
    patchWithCleanup,
} from '@web/../tests/helpers/utils';

import { useAiSession } from '@muk_ai/chat/session/use_ai_session';

class Probe extends Component {
    static template = xml`<div t-esc="session.state.status"/>`;
    static props = ['*'];
    setup() {
        this.session = useAiSession();
    }
}

QUnit.module('muk_ai', {}, function () {
    QUnit.module('run watch');

    QUnit.test(
        'a running chat on screen catches up with an end the bus never announced',
        async (assert) => {
            const intervals = new Map();
            let nextId = 0;
            patchWithCleanup(browser, {
                setInterval(fn) {
                    intervals.set(++nextId, fn);
                    return nextId;
                },
                clearInterval(id) {
                    intervals.delete(id);
                },
            });
            const tick = async () => {
                for (const fn of intervals.values()) {
                    fn();
                }
                await nextTick();
            };
            let state = 'running';
            const services = registry.category('services');
            const fake = (name, value) =>
                services.add(name, { start: () => value }, { force: true });
            services.add('orm', ormService, { force: true });
            fake(
                'bus_service',
                Object.assign(new EventTarget(), {
                    start() {},
                    addChannel() {},
                    deleteChannel() {},
                }),
            );
            fake('user', { userId: 1, context: {} });
            fake('notification', { add() {} });
            fake('action', { currentController: null, doAction() {} });
            fake('dialog', { add() {} });
            fake('muk_ai.session_notification', { markActive() {}, markInactive() {} });
            const env = await makeTestEnv({
                mockRPC(route, args) {
                    if (args.method === 'get_snapshot') {
                        assert.step('load');
                        return { id: 1, state, events: [] };
                    }
                    if (args.method === 'read') {
                        return [{ id: 1, user_id: 1, can_write: true, state }];
                    }
                },
            });
            const probe = await mount(Probe, getFixture(), { env });
            await probe.session.load(1);
            await nextTick();
            assert.verifySteps(['load']);
            await tick();
            assert.verifySteps([]);
            state = 'done';
            await tick();
            assert.verifySteps(['load']);
            assert.strictEqual(probe.session.state.status, 'done');
            assert.strictEqual(intervals.size, 0);
        },
    );
});
