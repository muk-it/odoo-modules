import { describe, expect, test } from '@odoo/hoot';
import { click, edit, queryAll, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat } from '@muk_ai/chat/chat';
import '@muk_ai_subagents/chat/run/chat_patch';

describe.current.tags('muk_ai_subagents');
defineMailModels();

const PARENT_ID = 7;
const CHILD_ID = 12;

const CHILD = {
    id: CHILD_ID,
    name: 'Bob: read the quarter',
    agent_name: 'Bob',
    color: 'blue',
    state: 'running',
    activity: 'Reading the sale orders',
    elapsed: 61,
    cost: 0.1,
};

const RUN = { children: [CHILD], total_cost: 0.1, cost_limit: 2 };

function record(id, name) {
    return {
        id,
        name,
        state: 'done',
        pending_ask: null,
        view_context: null,
        last_text: '',
        error_message: null,
        iteration_count: 1,
        total_input_tokens: 0,
        total_output_tokens: 0,
        last_input_tokens: 0,
        context_window: 8000,
        total_cost: 0,
        user_id: false,
        agent_id: false,
        override_approval_mode: false,
        effective_approval_mode: 'ask',
        pending_user_messages: [],
    };
}

function snapshot(events) {
    return {
        state: 'done',
        events,
        oldest_sequence: null,
        has_more_older: false,
        pending_ask: null,
        view_context: null,
        error_message: null,
        iteration_count: 1,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_cost: 0,
        last_input_tokens: 0,
        context_window: 8000,
        override_approval_mode: false,
        effective_approval_mode: 'ask',
        pending_user_messages: [],
    };
}

const PARENT_EVENTS = [
    { event_id: 1, kind: 'text', content: 'I will ask Bob.' },
    {
        event_id: 2,
        kind: 'delegation_start',
        payload: { children: [{ id: CHILD_ID, name: CHILD.name }] },
    },
];
const CHILD_EVENTS = [{ event_id: 9, kind: 'text', content: 'Read 40 orders.' }];

/**
 * Mount the full-page chat on a conversation that delegated to one subagent.
 * @returns {Promise<{chat: object, steers: Array}>} the chat and the steers sent
 */
async function mountChat() {
    const steers = [];
    onRpc('muk_ai.session', 'search_read', () => [
        {
            id: PARENT_ID,
            name: 'Demo',
            state: 'done',
            create_date: '2026-04-20 10:00:00',
        },
    ]);
    onRpc('muk_ai.session', 'read', ({ args }) => [
        record(args[0][0], args[0][0] === CHILD_ID ? CHILD.name : 'Demo'),
    ]);
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshot(args[0] === CHILD_ID ? CHILD_EVENTS : PARENT_EVENTS),
    );
    onRpc('muk_ai.session', 'subagent_run_snapshot', () => RUN);
    onRpc('muk_ai.session', 'subagent_peek', () => ({
        activity: CHILD.activity,
        question: '',
        calls: [],
    }));
    onRpc('muk_ai.session', 'subagent_steer', ({ args }) => {
        steers.push(args);
        return RUN;
    });
    onRpc('muk_ai.agent', 'search_read', () => []);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    onRpc('muk_ai.space', 'fetch_general_domain', () => [['space_id', '=', false]]);
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    mockService('notification', { add: () => {} });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(PARENT_ID);
    await animationFrame();
    return { chat, steers };
}

/** Open the one subagent of the run the way the user does: through the strip. */
async function openSubagent() {
    await click('.mk_run_strip_line');
    await animationFrame();
    await click('.mk_agent_row');
    await animationFrame();
    await click('.mk_agent_detail_open');
    await animationFrame();
    await animationFrame();
}

test('opening a subagent navigates to it and leaves one composer on screen', async () => {
    await mountChat();
    expect('.mk_messages_wrap').toHaveCount(1);
    expect('.mk_subagent_child').toHaveCount(0);

    await openSubagent();

    // the subagent takes the room the conversation had, rather than sitting
    // beside it in a panel of its own
    expect('.mk_messages_wrap').toHaveCount(0);
    expect('.mk_subagent_child').toHaveCount(1);
    expect('.mk_composer textarea').toHaveCount(1);
    // the crumb names the subagent once; its brief follows, muted
    expect(queryFirst('.mk_subagent_crumb_child').textContent).toBe('Bob');
    expect(queryFirst('.mk_subagent_crumb_agent').textContent).toBe('read the quarter');
    expect(queryAll('.mk_bubble_assistant').map((el) => el.textContent.trim())).toEqual(
        ['Read 40 orders.'],
    );
});

test('the composer names the subagent it writes to and sends to it', async () => {
    const { chat, steers } = await mountChat();
    await openSubagent();

    expect(queryFirst('.mk_composer textarea').placeholder).toBe(
        'Direct Bob — reaches it after its current step…',
    );
    await click('.mk_composer textarea');
    await edit('Only look at Q2.');
    await animationFrame();
    await click('.mk_send');
    await animationFrame();

    expect(steers).toEqual([[PARENT_ID, CHILD_ID, 'Only look at Q2.']]);
    expect(chat.session.state.input).toBe('');
});

test('the breadcrumb goes back to the conversation that delegated', async () => {
    const { chat } = await mountChat();
    await openSubagent();

    await click('.mk_subagent_back');
    await animationFrame();

    expect(chat.session.state.subagentOpen).toBe(null);
    expect('.mk_subagent_child').toHaveCount(0);
    expect('.mk_messages_wrap').toHaveCount(1);
    expect('.mk_composer textarea').toHaveCount(1);
});
