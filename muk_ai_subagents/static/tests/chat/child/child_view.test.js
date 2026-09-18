import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { SubagentChildView } from '@muk_ai_subagents/chat/child/child_view';

describe.current.tags('muk_ai_subagents');
defineMailModels();

const CHILD_ID = 12;

const OPEN = {
    id: CHILD_ID,
    name: 'Bob: read the quarter',
    agent_name: 'Bob',
    color: 'blue',
    state: 'running',
};

const EVENTS = [
    { event_id: 1, kind: 'user_message', content: 'Read the sale orders.' },
    {
        event_id: 2,
        kind: 'tool_call',
        name: 'search_read',
        call_id: 'c1',
        arguments: '{"model": "sale.order"}',
    },
    {
        event_id: 3,
        kind: 'tool_result',
        name: 'search_read',
        call_id: 'c1',
        result: '[{"id": 7}]',
        sources: [
            {
                id: 'record:sale.order,7',
                type: 'record',
                display_name: 'SO0007',
                href: '/odoo/sale.order/7',
            },
        ],
    },
    { event_id: 4, kind: 'text', content: 'Read **40** orders.' },
];

function snapshot() {
    return {
        state: 'done',
        events: EVENTS,
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

/** Mount the subagent transcript on a parent that has one open. */
async function mountChild() {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot());
    onRpc('muk_ai.session', 'read', () => [
        { id: CHILD_ID, name: OPEN.name, state: 'done' },
    ]);
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    mockService('notification', { add: () => {} });
    const parent = { state: { subagentOpen: OPEN } };
    const view = await mountWithCleanup(SubagentChildView, {
        props: { session: parent },
    });
    await animationFrame();
    return { view, parent };
}

/** Return the first block of `type` across the rendered transcript. */
function blockOf(view, type) {
    return view.renderedTurns
        .flatMap((turn) => turn.blocks || [])
        .find((block) => block.type === type);
}

test('a subagent transcript is its own conversation, not the parent one', async () => {
    const { view } = await mountChild();
    expect(view.open.id).toBe(CHILD_ID);
    expect(view.session.state.sessionId).toBe(CHILD_ID);
    expect(view.colorClass).toInclude('blue');
    expect(view.isCompact).toBe(false);
    expect(queryAll('.mk_bubble_user').map((el) => el.textContent.trim())).toEqual([
        'Read the sale orders.',
    ]);
    // markdown is rendered, not shown as asterisks
    expect(queryFirst('.mk_bubble_assistant').innerHTML).toInclude(
        '<strong>40</strong>',
    );
});

test('the calls the subagent made are cards of its own', async () => {
    const { view } = await mountChild();
    const tool = blockOf(view, 'tool');
    expect(tool.callId).toBe('c1');
    expect(view.turnRenderer(view.renderedTurns[0])).not.toBe(undefined);
    expect(view.isToolExpanded('c1')).toBe(false);
    view.toggleToolBlock('c1');
    await animationFrame();
    expect(view.isToolExpanded('c1')).toBe(true);
});

test('a finished call is never drawn as still streaming', async () => {
    const { view } = await mountChild();
    expect(view.isToolStreaming({ result: '[]' })).toBe(false);
    expect(view.isToolStreaming({ result: null })).toBe(false);
    expect(view.isToolHiddenForAsk({ result: '[]' }, { blocks: [] })).toBe(false);
});

test('a call whose answer is the question itself is not shown twice', async () => {
    // The ask renders as its own card, so the tool call behind it would be a
    // second, emptier copy of the same thing.
    const { view } = await mountChild();
    const turn = {
        blocks: [
            { type: 'tool', callId: 'c2', result: null },
            { type: 'ask', callId: 'c2' },
        ],
    };
    expect(view.isToolHiddenForAsk(turn.blocks[0], turn)).toBe(true);
    // the hidden call is never folded into a group with its neighbours, so
    // the group header can never count a card the transcript does not show
    const items = view.turnItems(turn);
    expect(items.map((item) => item.type)).toEqual(['tool', 'ask']);
});

test('the sources of a turn fold away and back, keyed per turn', async () => {
    const { view } = await mountChild();
    const turn = view.renderedTurns.find((entry) => (entry.sources || []).length);
    expect(turn.sources.map((source) => source.id)).toEqual(['record:sale.order,7']);
    expect(view.isTurnSourcesExpanded(turn, 0)).toBe(false);
    view.toggleTurnSources(turn, 0);
    await animationFrame();
    expect(view.isTurnSourcesExpanded(turn, 0)).toBe(true);
    expect(view.turnSourcesKey(turn, 0)).toBe(`e${turn.eventId}`);
    expect(view.turnSourcesKey({}, 3)).toBe('t3');
});

test('an ask card can be read as arguments or as a question', async () => {
    const { view } = await mountChild();
    const block = { type: 'ask', callId: 'c2', arguments: '{"question": "Which?"}' };
    const before = view.askViewMode(block);
    view.toggleAskView('c2');
    await animationFrame();
    expect(view.askViewMode(block)).not.toBe(before);
    expect(typeof view.askArgsText(block)).toBe('string');
    // a card with no call id has nothing to toggle
    view.toggleAskView(null);
    expect(view.askViewMode(block)).not.toBe(before);
});

test('the status shown is the one the subagent session reports', async () => {
    const { view } = await mountChild();
    expect(view.status).toBe(view.session.state.status);
    expect(view.statusIcon(view.status)).toInclude('fa-');
    expect(String(view.statusLabel(view.status))).not.toBe('');
    expect(view.statusBadgeClass(view.status)).not.toBe(undefined);
    expect(view.formatTimestamp('2026-04-20 10:00:00')).not.toBe('');
    expect(view.renderUserText(null)).toBe('');
    expect(view.renderUserText('plain')).toBe('plain');
    expect(String(view.renderAssistantMarkdown('**bold**'))).toInclude('<strong>');
});

test('going back closes the subagent on the parent', async () => {
    const { parent } = await mountChild();
    await click('.mk_subagent_back');
    await animationFrame();
    expect(parent.state.subagentOpen).toBe(null);
});
