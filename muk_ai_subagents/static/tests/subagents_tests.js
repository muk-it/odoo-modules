/** @odoo-module */

import { reactive } from '@odoo/owl';

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
import { ormService } from '@web/core/orm_service';
import { uiService } from '@web/core/ui/ui_service';

import { buildRenderedTurns, isToolBlockHidden } from '@muk_ai/chat/session/turns';
import { sessionEventHandlers } from '@muk_ai/chat/session/use_ai_session';
import { chatLists } from '@muk_ai/chat/utils';

import { activityText, reportLine } from '@muk_ai_subagents/chat/run/run';
import { SubagentBar } from '@muk_ai_subagents/chat/run_bar/run_bar';
import { SubagentRunCard } from '@muk_ai_subagents/chat/run_card/run_card';

QUnit.module('muk_ai_subagents', {}, function () {
    QUnit.module('subagents');

    const identity = (id, agent, objective, color) => ({
        id,
        name: `${agent}: ${objective}`,
        agent_name: agent,
        objective,
        color,
    });
    const RESEARCHER = identity(2, 'Researcher', 'Find leads', 'blue');
    const WRITER = identity(3, 'Writer', 'Draft the mail', 'green');
    const CLEANER = identity(4, 'Cleaner', 'Remove duplicates', 'orange');

    const entry = (child, values = {}) => ({
        ...child,
        call_id: 'd1',
        state: 'running',
        stop_reason: false,
        error: false,
        activity: false,
        repeating: false,
        ask: false,
        waiting_since: false,
        elapsed: 12,
        cost: 0.01,
        report: '',
        ...values,
    });

    const QUESTION = { kind: 'question', call_id: 'a1', text: 'Which tone?' };
    const APPROVAL = { kind: 'approval', call_id: 'c1', text: 'Deletes 2 contacts' };

    const live = () => ({
        children: [
            entry(RESEARCHER, {
                activity: { kind: 'tool_call', name: 'search_read', arguments: {} },
            }),
            entry(WRITER, { state: 'waiting', ask: QUESTION }),
            entry(CLEANER, { state: 'waiting', ask: APPROVAL }),
        ],
    });

    /**
     * Build the session api a chat surface hands its cards, recording its calls.
     * @param {object} assert the QUnit assert the calls are recorded on
     * @param {object} values the session state
     * @returns {object} the session
     */
    function fakeSession(assert, values = {}) {
        const state = reactive({ sessionId: 1, status: 'waiting', ...values });
        return {
            state,
            canWrite: () => true,
            isQueueing: () => state.status === 'running',
            callSession: async (method) => {
                assert.step(`${method} ${state.sessionId}`);
                return { id: state.sessionId };
            },
            applySnapshot: () => {},
        };
    }

    /**
     * Mount a run component with the services it uses, serving the actions on
     * the subagents and recording them with the chats opened.
     * @param {object} assert the QUnit assert the calls are recorded on
     * @param {object} Component the component to mount
     * @param {object} props its props
     * @returns {Promise<HTMLElement>} the fixture
     */
    async function mountRun(assert, Component, props) {
        const services = registry.category('services');
        services.add('ui', uiService);
        services.add('orm', ormService);
        services.add('notification', makeFakeNotificationService());
        services.add('action', { start: () => ({ doAction: () => {} }) });
        services.add('muk_ai.chat_window', {
            start: () => ({
                open: (id) => assert.step(`open ${id}`),
                close: () => {},
            }),
        });
        const env = await makeTestEnv({
            mockRPC: (route, { model, method, args: [id, ...rest] }) => {
                if (model === 'muk_ai.session') {
                    assert.step([method, id, ...rest].join(' '));
                    return {};
                }
            },
        });
        const target = getFixture();
        await mount(Component, target, { env, props });
        return target;
    }

    /**
     * Return the trimmed texts of the elements a selector matches.
     * @param {HTMLElement} target the fixture
     * @param {string} selector the selector
     * @returns {Array} the texts
     */
    function texts(target, selector) {
        return [...target.querySelectorAll(selector)].map((el) =>
            el.textContent.trim(),
        );
    }

    QUnit.test(
        'a live run puts who needs the user first and takes their answers in place',
        async (assert) => {
            const session = fakeSession(assert, { subagents: live() });
            const target = await mountRun(assert, SubagentBar, { session });
            assert.deepEqual(texts(target, '.mk_run_card_docked .mk_run_card_title'), [
                '2 need you · 1 of 3 working',
            ]);
            assert.deepEqual(texts(target, '.mk_run_row_agent'), [
                'Writer',
                'Cleaner',
                'Researcher',
            ]);
            const input = '.mk_run_row[data-child-id="3"] .mk_run_ask input';
            await editInput(target, input, 'Formal please');
            await triggerEvent(target, input, 'keydown', { key: 'Enter' });
            await click(
                target,
                '.mk_run_row[data-child-id="4"] .mk_ask_actions .btn-primary',
            );
            assert.verifySteps(['answer 3 Formal please', 'approve_tool 4']);
        },
    );

    QUnit.test(
        'a docked run folds its finished subagents away and follows the bus',
        async (assert) => {
            const session = fakeSession(assert, { subagents: live() });
            const target = await mountRun(assert, SubagentBar, { session });
            sessionEventHandlers.get('subagent_update')(
                {
                    children: [
                        entry(RESEARCHER, { state: 'done', stop_reason: 'done' }),
                        ...live().children.slice(1),
                    ],
                },
                { state: session.state },
            );
            await nextTick();
            assert.containsN(target, '.mk_run_card_docked .mk_run_row', 2);
            await click(target, '.mk_run_card_docked .mk_run_card_finished');
            assert.containsN(target, '.mk_run_card_docked .mk_run_row', 3);
            assert.deepEqual(
                texts(target, '.mk_run_card_docked .mk_run_card_finished'),
                ['Hide finished'],
            );
        },
    );

    QUnit.test(
        'a run in the transcript folds into its reports once every subagent ended',
        async (assert) => {
            const session = fakeSession(assert, {
                subagents: {
                    children: [
                        entry(RESEARCHER, {
                            state: 'done',
                            stop_reason: 'done',
                            elapsed: 65,
                            report: '**Three** leads\nAcme',
                        }),
                        entry(WRITER, {
                            state: 'done',
                            stop_reason: 'done',
                            report: 'Draft',
                        }),
                        entry(CLEANER, { state: 'error', stop_reason: 'no_progress' }),
                    ],
                },
            });
            const [, turn] = buildRenderedTurns([
                { kind: 'user_message', content: 'Go', event_id: 1 },
                {
                    kind: 'delegation_start',
                    call_id: 'd1',
                    children: [RESEARCHER, WRITER, CLEANER],
                    event_id: 2,
                },
            ]);
            const target = await mountRun(assert, SubagentRunCard, { turn, session });
            assert.deepEqual(texts(target, '.mk_run_card_title'), [
                '3 subagents reported in 1m 05s',
            ]);
            assert.containsNone(target, '.mk_run_card_stop_all');
            assert.deepEqual(texts(target, '.mk_run_row_line'), [
                'Stopped for repeating itself',
                'Three leads',
                'Draft',
            ]);
            await click(target, '.mk_run_row[data-child-id="2"] .mk_run_row_head');
            assert.deepEqual(
                texts(
                    target,
                    '.mk_run_row[data-child-id="2"] .mk_run_row_report strong',
                ),
                ['Three'],
            );
        },
    );

    QUnit.test(
        'a running subagent is opened beside the run and stopped one by one or all together',
        async (assert) => {
            const session = fakeSession(assert, { subagents: live() });
            const target = await mountRun(assert, SubagentBar, { session });
            await click(target, '.mk_run_row[data-child-id="2"] .mk_run_row_head');
            await click(target, '.mk_run_row[data-child-id="2"] .mk_run_row_open');
            await click(target, '.mk_run_row[data-child-id="2"] .mk_run_row_stop');
            await click(target, '.mk_run_card_stop_all');
            await nextTick();
            assert.verifySteps(['open 2', 'action_stop 2', 'action_stop_subagents 1']);
        },
    );

    QUnit.test('a subagent chat names the chat it works for', async (assert) => {
        const session = fakeSession(assert, {
            sessionId: 2,
            status: 'running',
            subagent_of: { ...RESEARCHER, parent_id: 1, parent_name: 'Campaign' },
        });
        const target = await mountRun(assert, SubagentBar, { session });
        assert.deepEqual(texts(target, '.mk_run_bar .mk_run_badge'), ['R']);
        assert.deepEqual(texts(target, '.mk_run_bar_hint'), [
            'Messages reach Researcher after its current step',
        ]);
        await click(target, '.mk_run_bar_parent');
        assert.verifySteps(['open 1']);
    });

    QUnit.test(
        'the delegate call is drawn by the run, and the subagents stay out of the lists',
        (assert) => {
            const [turn] = buildRenderedTurns([
                { kind: 'tool_call', name: 'delegate', call_id: 'd1', arguments: {} },
                {
                    kind: 'tool_result',
                    call_id: 'd1',
                    result: '{"status": "delegated"}',
                },
            ]);
            assert.ok(isToolBlockHidden(turn.blocks[0], turn));
            assert.deepEqual(chatLists.domain.at(-1), [
                'parent_session_id',
                '=',
                false,
            ]);
            assert.strictEqual(
                reportLine('| a | b |\n**Three** [leads](x)'),
                'Three leads',
            );
            assert.strictEqual(
                String(activityText({ repeating: true })),
                'Repeating the same call',
            );
        },
    );
});
