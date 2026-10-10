import { describe, expect, test } from '@odoo/hoot';
import { click, press, queryAllTexts } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { reactive } from '@odoo/owl';
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { buildRenderedTurns, isToolBlockHidden } from '@muk_ai/chat/session/turns';
import { sessionEventHandlers } from '@muk_ai/chat/session/use_ai_session';
import { chatLists } from '@muk_ai/chat/utils';

import { activityText, reportLine } from '@muk_ai_subagents/chat/run/run';
import { SubagentBar } from '@muk_ai_subagents/chat/run_bar/run_bar';
import { SubagentRunCard } from '@muk_ai_subagents/chat/run_card/run_card';

describe.current.tags('muk_ai_subagents');
defineMailModels();

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

const LIVE = {
    children: [
        entry(RESEARCHER, {
            activity: { kind: 'tool_call', name: 'search_read', arguments: {} },
        }),
        entry(WRITER, { state: 'waiting', ask: QUESTION }),
        entry(CLEANER, { state: 'waiting', ask: APPROVAL }),
    ],
};

/**
 * Build the session api a chat surface hands its cards, recording its calls.
 * @param {object} values the session state
 * @returns {object} the session
 */
function fakeSession(values = {}) {
    const state = reactive({ sessionId: 1, status: 'waiting', ...values });
    return {
        state,
        canWrite: () => true,
        isQueueing: () => state.status === 'running',
        callSession: async (method) => {
            expect.step(`${method} ${state.sessionId}`);
            return { id: state.sessionId };
        },
        applySnapshot: () => {},
    };
}

/**
 * Serve the actions on the subagents and record the chats opened.
 */
function serveChats() {
    for (const method of ['answer', 'approve_tool', 'action_stop']) {
        onRpc('muk_ai.session', method, ({ args: [id, ...rest] }) => {
            expect.step([method, id, ...rest].join(' '));
            return {};
        });
    }
    mockService('muk_ai.chat_window', {
        open: (id) => expect.step(`open ${id}`),
        close: () => {},
    });
}

test('a live run puts who needs the user first and takes their answers in place', async () => {
    serveChats();
    const session = fakeSession({ subagents: LIVE });
    await mountWithCleanup(SubagentBar, { props: { session } });
    expect('.mk_run_card_docked .mk_run_card_title').toHaveText(
        '2 need you · 1 of 3 working',
    );
    expect(queryAllTexts('.mk_run_row_agent')).toEqual([
        'Writer',
        'Cleaner',
        'Researcher',
    ]);
    await contains('.mk_run_row[data-child-id="3"] .mk_run_ask input').edit(
        'Formal please',
        { confirm: false },
    );
    await press('Enter');
    await contains(
        '.mk_run_row[data-child-id="4"] .mk_ask_actions .btn-primary',
    ).click();
    expect.verifySteps(['answer 3 Formal please', 'approve_tool 4']);
});

test('a docked run folds its finished subagents away and follows the bus', async () => {
    serveChats();
    const session = fakeSession({ subagents: LIVE });
    await mountWithCleanup(SubagentBar, { props: { session } });
    sessionEventHandlers.get('subagent_update')(
        {
            children: [
                entry(RESEARCHER, { state: 'done', stop_reason: 'done' }),
                ...LIVE.children.slice(1),
            ],
        },
        { state: session.state },
    );
    await animationFrame();
    expect('.mk_run_card_docked .mk_run_row').toHaveCount(2);
    await click('.mk_run_card_docked .mk_run_card_finished');
    await animationFrame();
    expect('.mk_run_card_docked .mk_run_row').toHaveCount(3);
    expect('.mk_run_card_docked .mk_run_card_finished').toHaveText('Hide finished');
});

test('a run in the transcript folds into its reports once every subagent ended', async () => {
    serveChats();
    const session = fakeSession({
        subagents: {
            children: [
                entry(RESEARCHER, {
                    state: 'done',
                    stop_reason: 'done',
                    elapsed: 65,
                    report: '**Three** leads\nAcme',
                }),
                entry(WRITER, { state: 'done', stop_reason: 'done', report: 'Draft' }),
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
    await mountWithCleanup(SubagentRunCard, { props: { turn, session } });
    expect('.mk_run_card_title').toHaveText('3 subagents reported in 1m 05s');
    expect('.mk_run_card_stop_all').toHaveCount(0);
    expect(queryAllTexts('.mk_run_row_line')).toEqual([
        'Stopped for repeating itself',
        'Three leads',
        'Draft',
    ]);
    await click('.mk_run_row[data-child-id="2"] .mk_run_row_head');
    await animationFrame();
    expect('.mk_run_row[data-child-id="2"] .mk_run_row_report strong').toHaveText(
        'Three',
    );
});

test('a running subagent is opened beside the run and stopped one by one or all together', async () => {
    serveChats();
    const session = fakeSession({ subagents: LIVE });
    await mountWithCleanup(SubagentBar, { props: { session } });
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_head').click();
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_open').click();
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_stop').click();
    await contains('.mk_run_card_stop_all').click();
    expect.verifySteps(['open 2', 'action_stop 2', 'action_stop_subagents 1']);
});

test('a subagent chat names the chat it works for', async () => {
    serveChats();
    const session = fakeSession({
        sessionId: 2,
        status: 'running',
        subagent_of: { ...RESEARCHER, parent_id: 1, parent_name: 'Campaign' },
    });
    await mountWithCleanup(SubagentBar, { props: { session } });
    expect('.mk_run_bar .mk_run_badge').toHaveText('R');
    expect('.mk_run_bar_hint').toHaveText(
        'Messages reach Researcher after its current step',
    );
    await contains('.mk_run_bar_parent').click();
    expect.verifySteps(['open 1']);
});

test('the delegate call is drawn by the run, and the subagents stay out of the lists', () => {
    patchTranslations();
    const [turn] = buildRenderedTurns([
        { kind: 'tool_call', name: 'delegate', call_id: 'd1', arguments: {} },
        { kind: 'tool_result', call_id: 'd1', result: '{"status": "delegated"}' },
    ]);
    expect(isToolBlockHidden(turn.blocks[0], turn)).toBe(true);
    expect(chatLists.domain.at(-1)).toEqual(['parent_session_id', '=', false]);
    expect(reportLine('| a | b |\n**Three** [leads](x)')).toBe('Three leads');
    expect(String(activityText({ repeating: true }))).toBe('Repeating the same call');
});
