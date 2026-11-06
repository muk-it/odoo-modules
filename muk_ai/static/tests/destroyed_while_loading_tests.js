// @odoo-module

import { Component, useState, xml } from '@odoo/owl';
import { hotkeyService } from '@web/core/hotkeys/hotkey_service';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { uiService } from '@web/core/ui/ui_service';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { makeFakeNotificationService } from '@web/../tests/helpers/mock_services';
import { getFixture, makeDeferred, mount, nextTick } from '@web/../tests/helpers/utils';

import { AIChat } from '@muk_ai/chat/chat';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

const TYPES = ['muk_ai.session_state', 'muk_ai.notification_badge', 'muk_ai.event'];

class Host extends Component {
    static template = xml`<t t-if="state.show"><t t-component="props.child" t-props="props.childProps"/></t>`;
    static props = ['*'];
    setup() {
        this.state = useState({ show: false });
    }
}

/**
 * Build a bus of the shape Odoo 16 has: one `notification` event for all types.
 * @returns {EventTarget} the bus, with `notify`
 */
function makeFakeBus() {
    return Object.assign(new EventTarget(), {
        start() {},
        addChannel() {},
        deleteChannel() {},
        notify(type, payload) {
            this.dispatchEvent(
                new CustomEvent('notification', { detail: [{ type, payload }] }),
            );
        },
    });
}

/**
 * Add the services the chat and the systray ask for and answer their RPCs.
 * @param {object} bus the fake bus
 * @param {string} heldMethod the RPC that stays open until `held` resolves
 * @param {object} held a deferred
 * @returns {Promise<object>} the environment
 */
function makeEnv(bus, heldMethod, held) {
    const services = registry.category('services');
    const fake = (name, value) =>
        services.add(name, { start: () => value }, { force: true });
    services.add('hotkey', hotkeyService, { force: true });
    services.add('ui', uiService, { force: true });
    services.add('orm', ormService, { force: true });
    services.add('notification', makeFakeNotificationService(), { force: true });
    fake('bus_service', bus);
    fake('action', { currentController: null, doAction() {} });
    fake('router', {
        current: { hash: {}, search: {} },
        pushState() {},
        replaceState() {},
    });
    fake('user', {
        userId: 1,
        name: 'Admin',
        context: {},
        hasGroup: async () => false,
    });
    fake('dialog', { add() {} });
    fake('muk_ai.session_notification', { markActive() {}, markInactive() {} });
    fake('muk_ai.chat_window', {
        state: { windows: [] },
        sessionIds: [],
        open() {},
        close() {},
        toggleMinimized() {},
        get activeSessionId() {
            return null;
        },
    });
    return makeTestEnv({
        mockRPC(route, args) {
            if (args.method === heldMethod) {
                return held;
            }
            if (args.method === 'notification_badge') {
                return { count: 0, session_ids: [], space_unread: {} };
            }
            if (args.model === 'muk_ai.session' && args.method === 'search_read') {
                return [
                    {
                        id: 7,
                        name: 'Open',
                        state: 'done',
                        create_date: '2026-04-21 10:00:00',
                    },
                ];
            }
            if (args.method === 'read') {
                return [{ id: 7, name: 'Open', state: 'done' }];
            }
            if (args.method === 'fetch_general_domain') {
                return [['space_id', '=', false]];
            }
            return [];
        },
    });
}

/**
 * Count the listeners still answering: each read of the payload is one.
 * @param {object} bus the fake bus
 * @returns {number} the reads
 */
function listening(bus) {
    let reads = 0;
    const payload = new Proxy(
        {},
        {
            get() {
                reads++;
                return undefined;
            },
        },
    );
    for (const type of TYPES) {
        try {
            bus.notify(type, payload);
        } catch {
            reads++;
        }
    }
    return reads;
}

/**
 * Show a component behind a host and destroy it while an RPC stays open.
 * @param {object} config `child`, `childProps`, the held `method`
 * @returns {Promise<object>} the bus and the host
 */
async function destroyWhileHeld({ child, childProps, method }) {
    const held = makeDeferred();
    const bus = makeFakeBus();
    const env = await makeEnv(bus, method, held);
    const host = await mount(Host, getFixture(), { env, props: { child, childProps } });
    host.state.show = true;
    await nextTick();
    await nextTick();
    host.state.show = false;
    await nextTick();
    held.resolve([]);
    await nextTick();
    await nextTick();
    return bus;
}

QUnit.module('muk_ai', {}, function () {
    QUnit.module('destroyed while loading');

    QUnit.test('a mounted systray does listen to the bus', async (assert) => {
        const bus = makeFakeBus();
        const env = await makeEnv(bus, 'none', makeDeferred());
        await mount(MukAISystray, getFixture(), { env });
        await nextTick();
        assert.ok(listening(bus) > 0);
    });

    QUnit.test(
        'a systray destroyed before it mounts stops listening to the bus',
        async (assert) => {
            const bus = await destroyWhileHeld({
                child: MukAISystray,
                childProps: {},
                method: 'get_needs_you',
            });
            assert.strictEqual(listening(bus), 0);
        },
    );

    QUnit.test(
        'a chat destroyed before it mounts stops listening to the bus',
        async (assert) => {
            const bus = await destroyWhileHeld({
                child: AIChat,
                childProps: { action: { params: {} } },
                method: 'get_snapshot',
            });
            assert.strictEqual(listening(bus), 0);
        },
    );
});
