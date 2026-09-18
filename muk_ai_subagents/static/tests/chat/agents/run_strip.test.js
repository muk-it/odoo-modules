import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { click, press, queryAll, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, reactive, xml } from '@odoo/owl';
import {
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { SubagentRunStrip } from '@muk_ai_subagents/chat/agents/run_strip';

describe.current.tags('muk_ai_subagents');
defineMailModels();

beforeEach(() => {
    patchTranslations();
});

/**
 * Stamp a roster time the way the backend does, in UTC without a zone.
 * @param {number} minutes how long ago
 * @returns {string} `YYYY-MM-DD HH:MM:SS`
 */
function minutesAgo(minutes) {
    const at = new Date(Date.now() - minutes * 60000);
    return at.toISOString().slice(0, 19).replace('T', ' ');
}

const DONE = {
    id: 11,
    name: 'Cy: count the orders',
    agent_name: 'Cy',
    color: 'green',
    state: 'done',
    stop_reason: 'done',
    elapsed: 40,
    cost: 0.02,
};
const WORKING = {
    id: 12,
    name: 'Bob: read the quarter',
    agent_name: 'Bob',
    color: 'blue',
    state: 'running',
    activity: 'Reading the sale orders of the last quarter to find the outliers',
    elapsed: 61,
    cost: 0.1,
};
const BLOCKED = {
    id: 13,
    name: 'Ada: update the partner',
    agent_name: 'Ada',
    color: 'red',
    state: 'waiting',
    waiting: { kind: 'approval', text: 'Write the record?' },
    waiting_since: minutesAgo(3),
    elapsed: 12,
    cost: 0.03,
};
const CHILDREN = [DONE, WORKING, BLOCKED];

/**
 * Build a reactive stand-in for the parent session api.
 * @param {Array} children the roster children
 * @param {object} [extra] more session state
 * @returns {object} the fake session
 */
function makeSession(children, extra = {}) {
    const state = reactive({
        sessionId: 7,
        subagentRun: {
            children,
            total_cost: 0.25,
            cost_limit: 2,
            receivedAt: Date.now(),
        },
        subagentOpen: null,
        subagentStripOpen: false,
        artifactsFocus: null,
        ...extra,
    });
    return {
        state,
        canWrite: () => true,
        focusArtifact(tab, itemId = null) {
            state.artifactsFocus = { tab, itemId };
        },
    };
}

/**
 * Mount the strip under a placeholder conversation.
 * @param {object} session the fake session
 * @returns {Promise<object>} the mounted parent
 */
async function mountStrip(session) {
    class Parent extends Component {
        static components = { SubagentRunStrip };
        static props = { session: { type: Object } };
        static template = xml`
            <div class="d-flex flex-column" style="width: 700px">
                <div class="fake_chat flex-grow-1" style="height: 200px">chat</div>
                <SubagentRunStrip session="props.session"/>
            </div>
        `;
    }
    return mountWithCleanup(Parent, { props: { session } });
}

test('the strip is one line until it is asked for more', async () => {
    await mountStrip(makeSession([DONE, WORKING]));
    expect('.mk_run_strip_line').toHaveCount(1);
    expect('.mk_run_strip_roster').toHaveCount(0);
    expect('.mk_agent_row').toHaveCount(0);
    expect(queryFirst('.mk_run_strip_text').textContent).toBe('1 subagent working');
    expect('.mk_run_strip_dots .mk_agent_dot').toHaveCount(2);
    expect('.mk_run_strip_cost').toHaveCount(0);
});

test('the run only mentions money once the ceiling is close', async () => {
    const session = makeSession([DONE, WORKING]);
    session.state.subagentRun.total_cost = 1.7;
    await mountStrip(session);
    const cost = queryFirst('.mk_run_strip_cost');
    expect(cost.textContent.replace(/\s+/g, ' ').trim()).toBe('1.70 / 2.00');
    expect(cost.classList.contains('mk_agents_cost_over')).toBe(false);
    session.state.subagentRun = { ...session.state.subagentRun, total_cost: 2.4 };
    await animationFrame();
    expect(
        queryFirst('.mk_run_strip_cost').classList.contains('mk_agents_cost_over'),
    ).toBe(true);
});

test('one rolled-up sentence is offered to assistive tech, not one per subagent', async () => {
    await mountStrip(makeSession(CHILDREN));
    const live = queryFirst('.mk_run_strip_live');
    expect(live.getAttribute('role')).toBe('status');
    expect(live.getAttribute('aria-atomic')).toBe('true');
    expect(live.textContent).toBe('Subagents: 1 working, 1 needing you, 1 done');
    expect('[aria-live], [role="status"]').toHaveCount(1);
});

test('nothing renders at all when the chat never delegated', async () => {
    await mountStrip(makeSession([]));
    expect('.mk_run_strip').toHaveCount(0);
});

test('a blocked subagent names itself and how long it has waited', async () => {
    await mountStrip(makeSession(CHILDREN));
    const line = queryFirst('.mk_run_strip_line');
    expect(line.classList.contains('mk_run_strip_blocked')).toBe(true);
    expect(line.classList.contains('mk_agent_red')).toBe(true);
    expect(queryFirst('.mk_run_strip_text').textContent).toInclude(
        'Ada has been waiting',
    );
});

test('a subagent repeating itself is called out before it ends', async () => {
    const stuck = { ...WORKING, stuck: true };
    await mountStrip(makeSession([DONE, stuck]));
    expect(queryFirst('.mk_run_strip_text').textContent).toBe(
        '1 subagent is repeating itself',
    );
    expect(
        queryFirst('.mk_run_strip_line').classList.contains('mk_run_strip_stuck'),
    ).toBe(true);
    await click('.mk_run_strip_line');
    await animationFrame();
    const row = queryFirst('.mk_agent_row[data-child-id="12"]');
    expect(row.classList.contains('mk_agent_row_stuck')).toBe(true);
    expect(row.querySelector('.fa-repeat')).not.toBe(null);
});

test('rows are ordered by what needs the user first', async () => {
    const failed = {
        id: 14,
        name: 'Ed: reconcile',
        agent_name: 'Ed',
        color: 'pink',
        state: 'stopped',
        stop_reason: 'no_progress',
        elapsed: 30,
    };
    await mountStrip(
        makeSession([DONE, WORKING, BLOCKED, failed], {
            subagentStripOpen: true,
        }),
    );
    const labels = queryAll('.mk_agents_section_label').map((n) =>
        n.textContent.trim(),
    );
    expect(labels).toEqual(['Needs you', 'Stopped early', 'Working', 'Done']);
    const names = queryAll('.mk_agent_row_name').map((n) => n.textContent.trim());
    expect(names).toEqual([
        'Ada: update the partner',
        'Ed: reconcile',
        'Bob: read the quarter',
        'Cy: count the orders',
    ]);
    const activity = queryFirst('.mk_agent_row_blocked .mk_agent_row_activity');
    expect(activity.textContent).toBe('Write the record?');
    expect(activity.classList.contains('text-truncate')).toBe(true);
});

test('finished rows fold into Done (n) once everything is idle', async () => {
    const idle = [
        { id: 1, name: 'Cy', color: 'green', state: 'done', stop_reason: 'done' },
        { id: 2, name: 'Di', color: 'cyan', state: 'done', stop_reason: '' },
        { id: 4, name: 'Flo', color: 'orange', state: 'done', stop_reason: 'done' },
    ];
    await mountStrip(
        makeSession(idle, {
            subagentStripOpen: true,
            subagentOpen: { id: 4, name: 'Flo', color: 'orange' },
        }),
    );
    let names = queryAll('.mk_agent_row_name').map((n) => n.textContent.trim());
    expect(names).toEqual(['Flo']);
    expect(queryFirst('.mk_agents_done_toggle').textContent.trim()).toBe('Done (2)');
    await click('.mk_agents_done_toggle');
    await animationFrame();
    names = queryAll('.mk_agent_row_name').map((n) => n.textContent.trim());
    expect(names).toEqual(['Flo', 'Cy', 'Di']);
});

test('opening a row shows its recent calls without moving the chat', async () => {
    onRpc('muk_ai.session', 'subagent_peek', ({ args }) => {
        expect(args).toEqual([7, 12]);
        return [
            { name: 'search_read', arguments: '{"model": "sale.order"}' },
            { name: 'read', arguments: '{"model": "res.partner"}' },
        ];
    });
    const session = makeSession(CHILDREN, { subagentStripOpen: true });
    await mountStrip(session);
    const chat = queryFirst('.fake_chat');
    const before = chat.getBoundingClientRect();
    await click('.mk_agent_row[data-child-id="12"]');
    await animationFrame();
    await animationFrame();
    const after = chat.getBoundingClientRect();
    expect(after.left).toBe(before.left);
    expect(after.width).toBe(before.width);
    expect(after.top).toBe(before.top);
    expect('.mk_agent_detail').toHaveCount(1);
    expect('.mk_agent_detail_call').toHaveCount(2);
    expect(queryFirst('.mk_agent_detail_call').textContent).toInclude('search_read');
    expect('.mk_agent_detail_stop').toHaveCount(1);
    await click('.mk_agent_detail_open');
    await animationFrame();
    expect(session.state.subagentOpen.id).toBe(12);
    expect(session.state.subagentStripOpen).toBe(false);
});

test('a row is keyboard reachable and Escape closes its detail', async () => {
    onRpc('muk_ai.session', 'subagent_peek', () => []);
    await mountStrip(makeSession(CHILDREN, { subagentStripOpen: true }));
    const row = queryFirst('.mk_agent_row[data-child-id="13"]');
    expect(row.getAttribute('role')).toBe('button');
    expect(row.getAttribute('tabindex')).toBe('0');
    row.focus();
    await press('Enter');
    await animationFrame();
    await animationFrame();
    expect('.mk_agent_detail').toHaveCount(1);
    await press('Escape');
    await animationFrame();
    expect('.mk_agent_detail').toHaveCount(0);
});

test('the footer shows the cost against its limit and stops the run', async () => {
    const stopped = [];
    onRpc('muk_ai.session', 'subagent_stop_all', ({ args }) => {
        stopped.push(args);
        return true;
    });
    await mountStrip(makeSession(CHILDREN, { subagentStripOpen: true }));
    expect(queryFirst('.mk_agents_cost').textContent.replace(/\s+/g, ' ').trim()).toBe(
        '0.250 / 2.00',
    );
    await click('.mk_agents_stop_all');
    await animationFrame();
    expect(stopped).toEqual([[7]]);
});

test('an idle run cannot be stopped', async () => {
    await mountStrip(
        makeSession([DONE], { subagentStripOpen: true, subagentOpen: null }),
    );
    expect(queryFirst('.mk_agents_stop_all').disabled).toBe(true);
    expect(queryFirst('.mk_run_strip_text').textContent).toBe('1 subagent done');
});
