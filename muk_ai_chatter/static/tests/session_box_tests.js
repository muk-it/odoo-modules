/** @odoo-module */

import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { click, getFixture, mount, nextTick } from '@web/../tests/helpers/utils';

import { AISessionBox } from '@muk_ai_chatter/chatter/session_box/session_box';

QUnit.module('muk_ai_chatter', {}, function () {
    QUnit.module('session_box');

    /**
     * Mount the box on a record, answering its summary with the given sessions,
     * and record the actions it runs and the session pushes it listens to.
     * @param {Function} entries builds the listed sessions from the current user id
     * @param {object} [options] the total of linked sessions and the props
     * @returns {Promise<object>} the target, the actions, the counts and a push function
     */
    async function mountBox(entries, { total, props = {} } = {}) {
        const actions = [];
        const totals = [];
        const bus = Object.assign(new EventTarget(), { start() {} });
        const summary = { count: 0, entries: [] };
        const services = registry.category('services');
        services.add('orm', ormService);
        services.add('bus_service', { start: () => bus });
        services.add('action', {
            start: () => ({ doAction: (action) => actions.push(action) }),
        });
        const env = await makeTestEnv({
            mockRPC: (route, { model, method, args }) => {
                if (model === 'res.partner' && method === 'get_ai_sessions_summary') {
                    summary.count += 1;
                    const listed = summary.entries;
                    return {
                        [args[0][0]]: {
                            entries: listed,
                            total: total ?? listed.length,
                        },
                    };
                }
            },
        });
        summary.entries = entries(env.services.user.userId).map((values) => ({
            id: 1,
            name: 'Session',
            state: 'done',
            create_date: '2026-01-02 09:30:00',
            user_id: [env.services.user.userId, 'Mitchell Admin'],
            agent_id: [1, 'Chatter Agent'],
            ...values,
        }));
        const target = getFixture();
        await mount(AISessionBox, target, {
            env,
            props: {
                threadModel: 'res.partner',
                threadId: 7,
                open: true,
                onLoaded: (count) => totals.push(count),
                ...props,
            },
        });
        const push = async (payload) => {
            const detail = [{ type: 'muk_ai.session_state', payload }];
            bus.dispatchEvent(new CustomEvent('notification', { detail }));
            await nextTick();
        };
        return { target, actions, totals, summary, push };
    }

    QUnit.test(
        'the box stays closed until asked for, and reports the count meanwhile',
        async (assert) => {
            const { target, totals } = await mountBox(() => [{ id: 1 }, { id: 2 }], {
                total: 7,
                props: { open: false },
            });
            assert.containsNone(target, '.mk_session_box');
            assert.deepEqual(totals, [7]);
        },
    );

    QUnit.test(
        'every session is listed, its state carried by the colour of a dot',
        async (assert) => {
            const { target } = await mountBox(() => [
                { id: 1, name: 'First run', state: 'done' },
                { id: 2, name: 'Second run', state: 'error', agent_id: false },
                { id: 3, name: 'Third run', state: 'exotic' },
            ]);
            const rows = [...target.querySelectorAll('.mk_session_box_item')];
            assert.deepEqual(
                rows.map(
                    (row) => row.querySelector('.mk_session_box_name').textContent,
                ),
                ['First run', 'Second run', 'Third run'],
            );
            assert.deepEqual(
                rows.map((row) =>
                    [...row.querySelector('.mk_session_box_state').classList].find(
                        (name) => name.startsWith('mk_state_'),
                    ),
                ),
                ['mk_state_done', 'mk_state_error', 'mk_state_idle'],
            );
            assert.deepEqual(
                rows.map((row) => row.title),
                ['Chatter Agent: Done', 'Error', 'Chatter Agent: exotic'],
            );
            assert.containsNone(target, '.mk_session_box_more');
        },
    );

    QUnit.test(
        'an own session opens its chat, a foreign one its form',
        async (assert) => {
            const { target, actions } = await mountBox((uid) => [
                { id: 7, name: 'Mine' },
                { id: 9, name: 'Theirs', user_id: [uid + 1, 'Other'] },
            ]);
            const [mine, theirs] = target.querySelectorAll('.mk_session_box_item');
            await click(mine);
            await click(theirs);
            assert.strictEqual(actions[0].tag, 'muk_ai.chat');
            assert.deepEqual(actions[0].params, { session_id: 7 });
            assert.strictEqual(actions[1].res_model, 'muk_ai.session');
            assert.strictEqual(actions[1].res_id, 9);
        },
    );

    QUnit.test(
        'a truncated list offers every session of the record',
        async (assert) => {
            const { target, actions } = await mountBox(() => [{ id: 4 }], {
                total: 12,
            });
            const more = target.querySelector('.mk_session_box_more');
            assert.strictEqual(more.textContent.trim(), 'View all 12 sessions');
            await click(more);
            assert.deepEqual(actions[0].domain, [
                ['res_model', '=', 'res.partner'],
                ['res_id', '=', 7],
            ]);
        },
    );

    QUnit.test(
        'the list follows its sessions and the ones started on its record',
        async (assert) => {
            const { push, summary } = await mountBox(() => [{ id: 5 }]);
            for (const [payload, count] of [
                [{ session_id: 4, res_model: 'res.partner', res_id: 8 }, 1],
                [{ session_id: 5, res_model: false, res_id: false }, 2],
                [{ session_id: 6, res_model: 'res.partner', res_id: 7 }, 3],
            ]) {
                await push({ state: 'running', ...payload });
                assert.strictEqual(summary.count, count);
            }
        },
    );
});
