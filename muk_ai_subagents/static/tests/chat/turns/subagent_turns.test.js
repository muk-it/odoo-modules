import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, markup, reactive, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { buildRenderedTurns, turnRendererFor } from '@muk_ai/chat/session/turns';

import {
    SubagentResultTurn,
    SubagentSpawnTurn,
    SubagentSteerTurn,
    buildResultTurn,
    buildSpawnTurn,
    buildSteerTurn,
} from '@muk_ai_subagents/chat/turns/subagent_turns';

describe.current.tags('muk_ai_subagents');
defineMailModels();

const START = {
    kind: 'delegation_start',
    event_id: 5,
    at: '2026-09-15 10:00:00',
    children: [
        { id: 1, name: 'Ada', agent_name: 'Writer', color: 'red' },
        { id: 2, name: 'Bob', agent_name: 'Reader', color: 'blue' },
        { id: 3, name: 'Cy', agent_name: 'Reader', color: 'green' },
    ],
};
const RESULT_OK = {
    kind: 'delegation_result',
    event_id: 9,
    child_id: 2,
    name: 'Bob',
    agent_name: 'Reader',
    color: 'blue',
    summary: 'Found 4 outliers.\n\nAll of them in Q2.',
    stop_reason: 'done',
    duration: 95,
    cost: 0.0421,
};
const RESULT_BAD = {
    ...RESULT_OK,
    event_id: 10,
    child_id: 1,
    name: 'Ada',
    color: 'red',
    stop_reason: 'cost_limit',
};

/**
 * Build a reactive stand-in for the parent session api.
 * @returns {object} the fake session
 */
function makeSession() {
    const state = reactive({ sessionId: 7, subagentOpen: null, artifactsFocus: null });
    return {
        state,
        canWrite: () => true,
        renderMarkdown: (text) => markup(`<p>${text}</p>`),
        focusArtifact(tab, itemId = null) {
            state.artifactsFocus = { tab, itemId };
        },
    };
}

async function mountTurn(turn, session) {
    class Parent extends Component {
        static components = {
            SubagentResultTurn,
            SubagentSpawnTurn,
            SubagentSteerTurn,
        };
        static props = { turn: { type: Object }, session: { type: Object } };
        static template = xml`
            <div class="mk_chat">
                <SubagentSpawnTurn t-if="props.turn.role === 'subagent_spawn'" turn="props.turn" session="props.session"/>
                <SubagentSteerTurn t-elif="props.turn.role === 'subagent_steer'" turn="props.turn" session="props.session"/>
                <SubagentResultTurn t-else="" turn="props.turn" session="props.session"/>
            </div>
        `;
    }
    return mountWithCleanup(Parent, { props: { turn, session } });
}

test('the builders turn delegation events into their own turns', () => {
    const turns = buildRenderedTurns([START, RESULT_OK, { kind: 'delegation_result' }]);
    expect(turns.map((turn) => turn.role)).toEqual([
        'subagent_spawn',
        'subagent_result',
    ]);
    expect(turns[0].eventId).toBe(5);
    expect(turns[0].children.length).toBe(3);
    expect(turns[1].childId).toBe(2);
    expect(turns[1].stopReason).toBe('done');
    expect(buildSpawnTurn({ children: [] })).toBe(null);
    expect(buildResultTurn({ name: 'x' })).toBe(null);
});

test('the registry resolves the renderers of the delegation turns', () => {
    expect(turnRendererFor({ role: 'subagent_spawn' })).toBe(SubagentSpawnTurn);
    expect(turnRendererFor({ role: 'subagent_result' })).toBe(SubagentResultTurn);
});

test('the spawn card is one line with a dot per child', async () => {
    const session = makeSession();
    await mountTurn(buildSpawnTurn(START), session);
    expect('.mk_subagent_spawn').toHaveCount(1);
    expect(queryFirst('.mk_subagent_spawn_label').textContent).toBe(
        'Delegated to 3 agents',
    );
    const dots = queryAll('.mk_subagent_spawn_dots .mk_agent_dot');
    expect(dots.length).toBe(3);
    expect(dots[0].classList.contains('mk_agent_red')).toBe(true);
    await click('.mk_subagent_spawn_line');
    await animationFrame();
    expect(session.state.subagentStripOpen).toBe(true);
});

test('a clean result starts collapsed and opens the child on demand', async () => {
    const session = makeSession();
    await mountTurn(buildResultTurn(RESULT_OK), session);
    expect('.mk_subagent_result_warning').toHaveCount(0);
    expect('.mk_subagent_result_open').toHaveCount(0);
    expect(queryFirst('.mk_subagent_result_summary').textContent).toBe(
        'Found 4 outliers.',
    );
    expect(queryFirst('.mk_subagent_result_duration').textContent).toBe('1m 35s');
    expect(queryFirst('.mk_subagent_result_cost').textContent).toBe('0.042');
    await click('.mk_subagent_result_head');
    await animationFrame();
    expect('.mk_subagent_result_open').toHaveCount(1);
    expect(queryFirst('.mk_subagent_result_summary_full').textContent).toInclude('Q2');
    await click('.mk_subagent_result_view');
    await animationFrame();
    expect(session.state.subagentOpen).toEqual({
        id: 2,
        name: 'Bob',
        agent_name: 'Reader',
        color: 'blue',
    });
});

test('a non-clean stop reason renders a warning and starts expanded', async () => {
    await mountTurn(buildResultTurn(RESULT_BAD), makeSession());
    expect('.mk_subagent_result_failed').toHaveCount(1);
    expect('.mk_subagent_result_open').toHaveCount(1);
    expect(queryFirst('.mk_subagent_result_warning').textContent).toInclude(
        'cost_limit',
    );
    expect('.mk_subagent_result_flag').toHaveCount(1);
    expect('.mk_subagent_result_summary_full').toHaveCount(1);
});

test('a steer event tells the parent which subagent was redirected', async () => {
    const entry = {
        kind: 'delegation_steer',
        event_id: 11,
        id: 2,
        name: 'Bob: read the quarter',
        agent_name: 'Reader',
        color: 'blue',
        text: 'Only look at Q2.',
    };
    const turn = buildSteerTurn(entry);
    expect(turn.role).toBe('subagent_steer');
    expect(turn.childId).toBe(2);
    await mountTurn(turn, makeSession());
    expect('.mk_subagent_steer').toHaveCount(1);
    expect(queryFirst('.mk_subagent_steer_label').textContent).toBe(
        'Reader was given more direction',
    );
    expect(queryFirst('.mk_subagent_steer_text').textContent).toBe('Only look at Q2.');
    expect(queryFirst('.mk_subagent_steer').classList.contains('mk_agent_blue')).toBe(
        true,
    );
});

test('a steer event without a subagent builds nothing', () => {
    expect(buildSteerTurn({ kind: 'delegation_steer', text: 'orphan' })).toBe(null);
});
