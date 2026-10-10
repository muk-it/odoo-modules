import { describe, expect, press, queryAllTexts, test } from '@odoo/hoot';
import {
    contains,
    fields,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import { ChatSidebar } from '@muk_ai/chat/sidebar/sidebar';
import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    AISessionModel,
    defineAIModels,
    emitEvent,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();
describe.current.tags('muk_ai_subagents');

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

const QUESTION = {
    kind: 'question',
    call_id: 'a1',
    text: 'Which tone?',
    options: ['Formal'],
    resolution: 'text',
};
const APPROVAL = {
    kind: 'approval',
    call_id: 'c1',
    text: 'Deletes 2 contacts',
    resolution: 'yesno',
    preview: { arguments: { ids: [7, 8] } },
};

const LIVE = {
    children: [
        entry(RESEARCHER, {
            activity: {
                kind: 'tool_call',
                name: 'search_read',
                arguments: { model: 'sale.order' },
            },
        }),
        entry(WRITER, { state: 'waiting', ask: QUESTION }),
        entry(CLEANER, { state: 'waiting', ask: APPROVAL }),
    ],
};

const askEvent = (ask) => ({ ...ask, kind: 'ask_user', event_id: 9, sequence: 9 });

const SNAPSHOTS = {
    1: {
        state: 'waiting',
        pending_ask: { kind: 'children', call_id: 'd1', queues_input: true },
        events: [
            {
                kind: 'user_message',
                content: 'Prepare the campaign',
                event_id: 1,
                sequence: 1,
            },
            {
                kind: 'tool_call',
                name: 'delegate',
                arguments: {},
                call_id: 'd1',
                event_id: 2,
                sequence: 2,
            },
            {
                kind: 'delegation_start',
                call_id: 'd1',
                children: [RESEARCHER, WRITER, CLEANER],
                event_id: 3,
                sequence: 3,
            },
        ],
        subagents: LIVE,
    },
    3: { state: 'waiting', pending_ask: QUESTION, events: [askEvent(QUESTION)] },
    4: { state: 'waiting', pending_ask: APPROVAL, events: [askEvent(APPROVAL)] },
    2: {
        name: 'Researcher: Find leads',
        state: 'running',
        events: [
            { kind: 'user_message', content: 'Objective: Find leads', event_id: 5 },
        ],
        subagent_of: { ...RESEARCHER, parent_id: 1, parent_name: 'Campaign' },
    },
};

/**
 * Serve the snapshots and record the actions on the chats.
 */
function serveChats() {
    onRpc('muk_ai.session', 'get_snapshot', ({ args: [id] }) =>
        snapshot({ id, ...SNAPSHOTS[id] }),
    );
    for (const method of [
        'answer',
        'approve_tool',
        'action_stop',
        'action_stop_subagents',
        'enqueue_message',
    ]) {
        onRpc('muk_ai.session', method, ({ args: [id, ...rest] }) => {
            expect.step([method, id, ...rest].join(' '));
            return snapshot({ id, ...SNAPSHOTS[id] });
        });
    }
}

/**
 * Show a chat in a conversation and record the chats opened from it.
 * @param {number} id the chat
 * @returns {Promise<object>} the session
 */
async function mountChat(id) {
    serveChats();
    const session = await openSession(id);
    patchWithCleanup(getService(AIChatPlugin), {
        openWindow: (opened) => expect.step(`open ${opened}`),
        openFullChat: (opened) => expect.step(`open ${opened}`),
    });
    await mountWithCleanup(ChatConversation, { props: { session } });
    return session;
}

test('a live run puts who needs the user first and takes their answers in place', async () => {
    await mountChat(1);
    expect('.mk_tool').toHaveCount(0);
    expect('.mk_run_card_docked .mk_run_card_title').toHaveText(
        '2 need you · 1 of 3 working',
    );
    expect(queryAllTexts('.mk_run_row_agent')).toEqual([
        'Writer',
        'Cleaner',
        'Researcher',
    ]);
    expect('.mk_run_row[data-child-id="2"] .mk_run_row_line').toHaveText(
        'Search Order',
    );
    await contains('.mk_run_row[data-child-id="3"] .mk_run_ask input').edit(
        'Formal please',
        {
            confirm: false,
        },
    );
    await press('Enter');
    await contains(
        '.mk_run_row[data-child-id="4"] .mk_ask_actions .btn-primary',
    ).click();
    expect.verifySteps(['answer 3 Formal please', 'approve_tool 4']);
});

test('a live run sits above the composer and folds its finished subagents away', async () => {
    await mountChat(1);
    await emitEvent(1, 'subagent_update', {
        ...LIVE,
        children: [
            entry(RESEARCHER, { state: 'done', stop_reason: 'done', report: 'Leads' }),
            ...LIVE.children.slice(1),
        ],
    });
    expect('.mk_messages .mk_run_card .mk_run_row').toHaveCount(0);
    expect('.mk_composer_wrap .mk_run_card_docked .mk_run_row').toHaveCount(2);
    await contains('.mk_run_card_docked .mk_run_card_finished').click();
    expect('.mk_run_card_docked .mk_run_row').toHaveCount(3);
    expect('.mk_run_card_docked .mk_run_card_finished').toHaveText('Hide finished');
});

test('a run follows the bus and folds into its reports once every subagent ended', async () => {
    await mountChat(1);
    await emitEvent(1, 'subagent_update', {
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
                report: 'Draft ready',
            }),
            entry(CLEANER, {
                state: 'error',
                stop_reason: 'no_progress',
                report: 'Found duplicates',
            }),
        ],
    });
    expect('.mk_run_card_title').toHaveText('3 subagents reported in 1m 05s');
    expect('.mk_run_bar, .mk_run_card_stop_all').toHaveCount(0);
    expect(queryAllTexts('.mk_run_row_line')).toEqual([
        'Stopped for repeating itself',
        'Three leads',
        'Draft ready',
    ]);
    expect('.mk_run_row_report').toHaveCount(1);
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_head').click();
    expect('.mk_run_row[data-child-id="2"] .mk_run_row_report strong').toHaveText(
        'Three',
    );
});

test('a running subagent is opened beside the run and stopped one by one or all together', async () => {
    await mountChat(1);
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_head').click();
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_open').click();
    await contains('.mk_run_row[data-child-id="2"] .mk_run_row_stop').click();
    await contains('.mk_run_card_stop_all').click();
    expect.verifySteps(['open 2', 'action_stop 2', 'action_stop_subagents 1']);
});

test('a subagent chat names the chat it works for and queues direction for its next step', async () => {
    await mountChat(2);
    expect('.mk_run_bar .mk_run_badge').toHaveText('R');
    expect('.mk_run_bar_hint').toHaveText(
        'Messages reach Researcher after its current step',
    );
    await contains('.mk_composer textarea').edit('Only this year', { confirm: false });
    await press('Enter');
    await contains('.mk_run_bar_parent').click();
    expect.verifySteps(['enqueue_message 2 Only this year', 'open 1']);
});

test('the subagents of a chat stay out of the chat list', async () => {
    AISessionModel._fields.parent_session_id = fields.Many2one({
        relation: 'muk_ai.session',
    });
    AISessionModel._records = [
        { id: 1, name: 'Campaign', state: 'waiting' },
        {
            id: 2,
            name: 'Researcher: Find leads',
            state: 'running',
            parent_session_id: 1,
        },
    ];
    await mountWithCleanup(ChatSidebar, {
        props: { onSelect: () => {}, onNew: () => {} },
    });
    expect(queryAllTexts('.mk_sidebar_name')).toEqual(['Campaign']);
});
