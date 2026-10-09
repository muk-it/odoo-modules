/** @odoo-module */

import { Component, useState, xml } from '@odoo/owl';

import { hotkeyService } from '@web/core/hotkeys/hotkey_service';
import { ormService } from '@web/core/orm_service';
import { registry } from '@web/core/registry';
import { makeTestEnv } from '@web/../tests/helpers/mock_env';
import { makeFakeNotificationService } from '@web/../tests/helpers/mock_services';
import {
    click,
    editInput,
    getFixture,
    mount,
    nextTick,
    triggerEvent,
} from '@web/../tests/helpers/utils';

import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';
import { insertFor } from '@muk_ai_chatter/composer/insert_button/insert_button';

QUnit.module('muk_ai_chatter', {}, function () {
    QUnit.module('compose_panel');

    const DRAFT = 'Dear customer, thanks for you order.';

    const SELECTION = 'thanks for you order';

    const SKILLS = [
        {
            name: 'shorten',
            label: 'Shorten',
            icon: 'fa-compress',
            category: 'rewrite',
            body: 'Shorten it.',
        },
        {
            name: 'grammar',
            label: 'Fix grammar',
            icon: 'fa-check',
            category: 'fix',
            body: 'Fix it.',
        },
        {
            name: 'reply',
            label: 'Reply',
            icon: 'fa-reply',
            category: 'generate',
            body: 'Reply to it.',
        },
    ];

    /**
     * Stub the server, the session bus and the chat windows the panel talks to,
     * and record what it was asked.
     * @returns {Promise<{calls: object, env: object}>} the calls made, and the env
     */
    async function setup() {
        const bus = Object.assign(new EventTarget(), {
            start() {},
            addChannel() {},
            deleteChannel() {},
        });
        const calls = {
            windows: [],
            opened: [],
            context: [],
            sent: [],
            saved: [],
            detached: false,
            discarded: false,
            openFails: false,
            state: 'done',
            answer: 'A better sentence.',
            emit: async (type, payload) => {
                const event = { session_id: 1, type, payload };
                const detail = [{ type: 'muk_ai.event', payload: event }];
                bus.dispatchEvent(new CustomEvent('notification', { detail }));
                await nextTick();
                await nextTick();
            },
        };
        const services = registry.category('services');
        services.add('orm', ormService);
        services.add('hotkey', hotkeyService);
        services.add('notification', makeFakeNotificationService());
        services.add('action', { start: () => ({ doAction() {} }) });
        services.add('bus_service', { start: () => bus });
        services.add('muk_ai.chat_window', {
            start: () => ({
                open: (id) => calls.windows.push(id),
                close: (id) =>
                    (calls.windows = calls.windows.filter((open) => open !== id)),
            }),
        });
        const answers = {
            'muk_ai.skill.fetch_skills': () => structuredClone(SKILLS),
            'muk_ai.session.open_for_composer': ({ kwargs }) => {
                if (calls.openFails) {
                    throw new Error('no agent available');
                }
                const { context: _context, ...values } = kwargs;
                calls.opened.push(values);
                return { id: 1 };
            },
            'muk_ai.session.update_compose_context': ({ args }) => {
                calls.context.push({ draft: args[1], selection: args[2] });
                return true;
            },
            'muk_ai.session.send_message': ({ args }) => {
                calls.sent.push(args[1]);
                return { id: 1, state: 'running' };
            },
            'muk_ai.session.discard_unused_composer': () => (calls.discarded = true),
            'muk_ai.session.detach_from_composer': () => (calls.detached = true),
            'muk_ai.session.read': () => [
                {
                    id: 1,
                    last_text: calls.answer,
                    state: calls.state,
                    error_message: 'Boom: x',
                },
            ],
            'muk_ai.skill.save_composer_prompt': ({
                args: [label, body, category],
            }) => {
                calls.saved.push([label, body, category]);
                return { name: 'saved', label, body, category, icon: 'fa-pencil' };
            },
        };
        const env = await makeTestEnv({
            mockRPC: (route, args) => answers[`${args.model}.${args.method}`]?.(args),
        });
        return { calls, env };
    }

    /**
     * Build an adapter standing in for a composer, recording what is applied.
     * @param {string} [selection] the text the user had selected
     * @param {string} [draft] everything already written in the composer
     * @returns {object} the adapter, with an `applied` log
     */
    function makeAdapter(selection = '', draft = '') {
        return {
            interfaceKey: 'mail_composer',
            applied: [],
            getDraft: () => draft,
            getSelection: () => selection,
            applySelection(text) {
                this.applied.push(['selection', text]);
            },
            applyDraft(text) {
                this.applied.push(['draft', text]);
            },
            replaceDraft(text) {
                this.applied.push(['replaced', text]);
            },
            getRecord: () => ({ resModel: 'res.partner', resId: 7 }),
            isAlive: () => true,
        };
    }

    /**
     * Hold panels that can be taken away again, as closing a composer does.
     */
    class PanelHolder extends Component {
        static components = { ComposePanel };
        static props = {};
        static template = xml`
        <div class="mk_test_holder">
            <t t-foreach="state.panels" t-as="panel" t-key="panel.id">
                <ComposePanel adapter="panel.adapter" close="() => this.close(panel)"/>
            </t>
        </div>`;
        setup() {
            this.state = useState({ panels: [] });
        }
        close(panel) {
            this.state.panels = this.state.panels.filter((entry) => entry !== panel);
        }
    }

    /**
     * Mount a panel over an adapter.
     * @param {object} env the test environment
     * @param {string} [selection] the text the user had selected
     * @param {string} [draft] everything already written in the composer
     * @returns {Promise<{holder: PanelHolder, adapter: object, target: HTMLElement}>} the fixture
     */
    async function mountPanel(env, selection = '', draft = '') {
        const adapter = makeAdapter(selection, draft);
        const target = document.createElement('div');
        getFixture().append(target);
        const holder = await mount(PanelHolder, target, { env });
        holder.state.panels.push({ id: 1, adapter });
        await nextTick();
        await nextTick();
        return { holder, adapter, target };
    }

    /**
     * Close every panel a holder shows.
     * @param {PanelHolder} holder the holder to empty
     */
    async function closeAll(holder) {
        holder.state.panels = [];
        await nextTick();
    }

    /**
     * Return the texts of the elements a selector matches.
     * @param {HTMLElement} target where to look
     * @param {string} selector what to look for
     * @returns {string[]} their texts
     */
    function texts(target, selector) {
        return [...target.querySelectorAll(selector)].map((el) =>
            el.textContent.trim(),
        );
    }

    /**
     * Pick the first offer of the panel, opening its group when it has one.
     * @param {HTMLElement} target the panel's container
     */
    async function pickFirst(target) {
        for (const selector of ['.mk_compose_panel_action', '.mk_compose_panel_chip']) {
            const offer = target.querySelector(selector);
            if (offer) {
                await click(offer);
            }
        }
        await nextTick();
    }

    /**
     * Type a line in an input of the panel and confirm it with Enter.
     * @param {HTMLElement} target the panel's container
     * @param {string} selector the input
     * @param {string} value what is typed
     */
    async function submit(target, selector, value) {
        await editInput(target, selector, value);
        await triggerEvent(target, selector, 'keydown', { key: 'Enter' });
        await nextTick();
    }

    QUnit.test('what is offered follows what is already written', async (assert) => {
        const { env } = await setup();
        for (const [selection, draft, actions, modifiers] of [
            ['', '', [], 3],
            [SELECTION, DRAFT, ['Fix grammar', 'Shorten'], 0],
            ['', DRAFT, ['Fix grammar', 'Shorten'], 0],
        ]) {
            const { holder, target } = await mountPanel(env, selection, draft);
            assert.deepEqual(texts(target, '.mk_compose_panel_action'), actions);
            assert.containsN(target, '.mk_compose_panel_quote', draft ? 1 : 0);
            if (actions.length) {
                await click(target, '.mk_compose_panel_action:last-child');
            }
            assert.containsN(target, '.mk_compose_panel_length', modifiers);
            assert.containsN(target, '.mk_compose_panel_tone', modifiers);
            await closeAll(holder);
        }
    });

    QUnit.test(
        'the session opens with the text and the record, and a whole draft is the target',
        async (assert) => {
            const { calls, env } = await setup();
            const { target } = await mountPanel(env, '', DRAFT);
            assert.deepEqual(calls.opened, [
                {
                    interface_key: 'mail_composer',
                    res_model: 'res.partner',
                    res_id: 7,
                    draft: DRAFT,
                    selection: '',
                },
            ]);
            await pickFirst(target);
            assert.deepEqual(calls.context, [{ draft: DRAFT, selection: DRAFT }]);
            assert.deepEqual(calls.sent, ['Fix it.']);
        },
    );

    QUnit.test(
        'the chosen length and tone are carried into a message written from nothing',
        async (assert) => {
            const { calls, env } = await setup();
            const { target } = await mountPanel(env);
            await click(target, '.mk_compose_panel_length:last-child');
            await click(target, '.mk_compose_panel_tone:last-child');
            await pickFirst(target);
            assert.strictEqual(
                calls.sent[0],
                'Reply to it. Take a little more room. Write in a warm, friendly tone.',
            );
        },
    );

    QUnit.test(
        'the answer streams in, and is put where the user was writing once accepted',
        async (assert) => {
            const { calls, env } = await setup();
            for (const [selection, draft, answer, applied, text = answer] of [
                [SELECTION, DRAFT, 'thank you for your order', 'selection'],
                [` ${SELECTION} `, DRAFT, 'thank you', 'selection', ' thank you '],
                ['', DRAFT, 'Dear customer, thank you.', 'replaced'],
                ['', '', 'A fresh message.', 'draft'],
            ]) {
                calls.answer = answer;
                const { holder, adapter, target } = await mountPanel(
                    env,
                    selection,
                    draft,
                );
                await pickFirst(target);
                await calls.emit('text_delta', { delta: 'Half ' });
                assert.strictEqual(
                    target.querySelector('.mk_compose_panel_stream').textContent,
                    'Half ',
                );
                await calls.emit('state', { state: 'done' });
                assert.containsN(target, '.mk_compose_panel_diff', draft ? 1 : 0);
                assert.deepEqual(adapter.applied, []);
                await click(target, '.mk_compose_panel_accept');
                assert.deepEqual(adapter.applied, [[applied, text]]);
                assert.strictEqual(holder.state.panels.length, 0);
            }
        },
    );

    QUnit.test('a discarded answer never reaches the composer', async (assert) => {
        const { calls, env } = await setup();
        const { adapter, target } = await mountPanel(env, SELECTION, DRAFT);
        await pickFirst(target);
        await calls.emit('state', { state: 'done' });
        await click(target, '.mk_compose_panel_discard');
        assert.containsN(target, '.mk_compose_panel_action', 2);
        assert.deepEqual(adapter.applied, []);
    });

    QUnit.test('a run that fails or answers nothing says so', async (assert) => {
        const { calls, env } = await setup();
        const { target } = await mountPanel(env, SELECTION, DRAFT);
        calls.state = 'error';
        await pickFirst(target);
        await calls.emit('state', { state: 'error' });
        assert.strictEqual(
            target.querySelector('.mk_compose_panel_error').textContent.trim(),
            'Boom',
        );
        Object.assign(calls, { state: 'done', answer: '' });
        await pickFirst(target);
        await calls.emit('state', { state: 'done' });
        assert.strictEqual(
            target.querySelector('.mk_compose_panel_error').textContent.trim(),
            'The agent returned nothing.',
        );
    });

    QUnit.test(
        'a done announced from the middle of a run is not taken as the answer',
        async (assert) => {
            const { calls, env } = await setup();
            calls.state = 'running';
            const { target } = await mountPanel(env, SELECTION, DRAFT);
            await pickFirst(target);
            await calls.emit('state', { state: 'done' });
            assert.containsOnce(target, '.mk_compose_panel_busy');
            calls.state = 'done';
            await calls.emit('state', { state: 'running' });
            await calls.emit('state', { state: 'done' });
            assert.containsOnce(target, '.mk_compose_panel_accept');
        },
    );

    QUnit.test(
        'only a helper nobody asked anything is dropped when the panel closes',
        async (assert) => {
            const { calls, env } = await setup();
            const first = await mountPanel(env, SELECTION, DRAFT);
            await closeAll(first.holder);
            assert.ok(calls.discarded);
            calls.discarded = false;
            const second = await mountPanel(env, SELECTION, DRAFT);
            await pickFirst(second.target);
            await closeAll(second.holder);
            assert.notOk(calls.discarded);
        },
    );

    QUnit.test(
        'the chips still work after the session failed to open',
        async (assert) => {
            const { calls, env } = await setup();
            calls.openFails = true;
            const { target } = await mountPanel(env, SELECTION, DRAFT);
            assert.containsOnce(target, '.mk_compose_panel_error');
            calls.openFails = false;
            await pickFirst(target);
            assert.deepEqual(calls.sent, ['Fix it.']);
        },
    );

    QUnit.test('a second helper closes the one already open', async (assert) => {
        const { env } = await setup();
        const { holder, target } = await mountPanel(env, SELECTION, DRAFT);
        holder.state.panels.push({ id: 2, adapter: makeAdapter() });
        await nextTick();
        await nextTick();
        assert.containsOnce(target, '.mk_compose_panel');
        assert.strictEqual(holder.state.panels[0].id, 2);
    });

    QUnit.test(
        'the chat window takes the session over, and puts its answers back',
        async (assert) => {
            const { calls, env } = await setup();
            const { holder, adapter, target } = await mountPanel(env, SELECTION, DRAFT);
            await click(target, '.mk_compose_panel_chat');
            await nextTick();
            assert.ok(calls.detached);
            assert.deepEqual(calls.windows, [1]);
            assert.strictEqual(holder.state.panels.length, 0);
            insertFor(1)('From the chat');
            assert.deepEqual(adapter.applied, [['selection', 'From the chat']]);
            assert.deepEqual(calls.windows, []);
        },
    );

    QUnit.test(
        'a free-text ask that worked can be kept as a quick action',
        async (assert) => {
            const { calls, env } = await setup();
            for (const [draft, category] of [
                ['', 'generate'],
                [DRAFT, 'rewrite'],
            ]) {
                const { holder, target } = await mountPanel(env, '', draft);
                await submit(target, '.mk_compose_panel_custom', 'Chase the payment');
                await calls.emit('state', { state: 'done' });
                await click(target, '.mk_compose_panel_save_open');
                await submit(target, '.mk_compose_panel_save_label', 'Chase');
                assert.deepEqual(calls.saved.at(-1), [
                    'Chase',
                    'Chase the payment',
                    category,
                ]);
                assert.containsOnce(target, '.mk_compose_panel_saved');
                await closeAll(holder);
            }
            const { target } = await mountPanel(env, SELECTION, DRAFT);
            await pickFirst(target);
            await calls.emit('state', { state: 'done' });
            assert.containsNone(target, '.mk_compose_panel_save_open');
        },
    );

    QUnit.test(
        'a quick action can be written from scratch, and escape folds the form',
        async (assert) => {
            const { calls, env } = await setup();
            const { target } = await mountPanel(env);
            await click(target, '.mk_compose_panel_new');
            await editInput(target, '.mk_compose_panel_create_label', 'Thank them');
            await editInput(
                target,
                '.mk_compose_panel_create_body',
                'Thank the customer.',
            );
            await click(target, '.mk_compose_panel_create_confirm');
            await nextTick();
            assert.deepEqual(calls.saved, [
                ['Thank them', 'Thank the customer.', 'generate'],
            ]);
            await click(target, '.mk_compose_panel_new');
            await triggerEvent(target, '.mk_compose_panel_create_label', 'keydown', {
                key: 'Escape',
            });
            assert.containsNone(target, '.mk_compose_panel_create');
            assert.containsOnce(target, '.mk_compose_panel');
        },
    );
});
