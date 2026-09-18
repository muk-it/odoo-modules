import { describe, expect, test } from '@odoo/hoot';
import { click, edit, press, queryAll, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, reactive, xml } from '@odoo/owl';
import {
    makeServerError,
    mockService,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { SubagentEscalations } from '@muk_ai_subagents/chat/escalation/escalation_card';

describe.current.tags('muk_ai_subagents');
defineMailModels();

const APPROVAL = {
    id: 31,
    name: 'Writer: update the partner',
    agent_name: 'Writer',
    color: 'purple',
    state: 'waiting',
    waiting: {
        kind: 'approval',
        text: 'Update the partner?',
        call_id: 'c1',
        preview: {
            kind: 'update',
            title: 'Update 1 contact',
            targets: [{ id: 5, display_name: 'Deco Addict' }],
            changes: [{ field: 'phone', label: 'Phone', from: '', to: '+43 1' }],
        },
    },
};
const QUESTION = {
    id: 32,
    name: 'Bob',
    color: 'cyan',
    state: 'waiting',
    waiting: { kind: 'question', text: 'Which quarter?', options: ['Q1', 'Q2'] },
};
const WORKING = { id: 33, name: 'Cy', color: 'green', state: 'running' };

/**
 * Build a reactive stand-in for the parent session api.
 * @param {Array} children the roster children
 * @param {boolean} [writable] whether the current user may steer the chat
 * @returns {object} the fake session
 */
function makeSession(children, writable = true) {
    const state = reactive({
        sessionId: 7,
        subagentRun: { children, receivedAt: Date.now() },
        subagentOpen: null,
        artifactsFocus: null,
    });
    return {
        state,
        canWrite: () => writable,
        focusArtifact(tab, itemId = null) {
            state.artifactsFocus = { tab, itemId };
        },
    };
}

async function mountCards(session) {
    class Parent extends Component {
        static components = { SubagentEscalations };
        static props = { session: { type: Object } };
        static template = xml`
            <div class="mk_chat">
                <SubagentEscalations session="props.session"/>
            </div>
        `;
    }
    return mountWithCleanup(Parent, { props: { session } });
}

test('one card per blocked child, labelled with its name and colour', async () => {
    await mountCards(makeSession([WORKING, APPROVAL, QUESTION]));
    expect('.mk_subagent_escalation').toHaveCount(2);
    const first = queryFirst('.mk_subagent_escalation[data-child-id="31"]');
    expect(first.classList.contains('mk_agent_purple')).toBe(true);
    expect(first.querySelector('.mk_ask_head strong').textContent).toBe(
        'Writer needs your confirmation',
    );
    expect(first.querySelector('.mk_ask_card')).not.toBe(null);
    expect(first.querySelector('.mk_ask_preview .mk_ask_title').textContent).toBe(
        'Update 1 contact',
    );
    const second = queryFirst('.mk_subagent_escalation[data-child-id="32"]');
    expect(second.querySelector('.mk_ask_head strong').textContent).toBe('Bob asks');
    expect(queryAll('.mk_subagent_option', { root: second }).length).toBe(2);
});

test('the approval buttons call the child session, not the parent', async () => {
    const calls = [];
    for (const method of ['approve_tool', 'approve_for_session', 'reject_tool']) {
        onRpc('muk_ai.session', method, ({ args }) => {
            calls.push([method, args]);
            return true;
        });
    }
    await mountCards(makeSession([APPROVAL]));
    await click('.mk_subagent_approve');
    await animationFrame();
    await click('.mk_subagent_approve_session');
    await animationFrame();
    await click('.mk_subagent_reject');
    await animationFrame();
    expect(calls.map(([method]) => method)).toEqual([
        'approve_tool',
        'approve_for_session',
        'reject_tool',
    ]);
    for (const [, args] of calls) {
        expect(args).toEqual([31]);
    }
});

test('an option or a typed reply answers the child by id', async () => {
    const answers = [];
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        answers.push(args);
        return true;
    });
    await mountCards(makeSession([QUESTION]));
    await click('.mk_subagent_option:first-child');
    await animationFrame();
    await click('.mk_subagent_answer_input');
    await edit('The last one');
    await animationFrame();
    await click('.mk_subagent_answer_send');
    await animationFrame();
    expect(answers).toEqual([
        [32, 'Q1'],
        [32, 'The last one'],
    ]);
});

test('a shared chat shows the cards without their buttons', async () => {
    await mountCards(makeSession([APPROVAL], false));
    expect('.mk_subagent_escalation').toHaveCount(1);
    expect('.mk_subagent_approve').toHaveCount(0);
    expect(queryFirst('.mk_ask_resolved').textContent).toInclude('owner');
});

test('the cards follow the roster arriving over the bus', async () => {
    const session = makeSession([WORKING, APPROVAL, QUESTION]);
    await mountCards(session);
    expect('.mk_subagent_escalation').toHaveCount(2);
    session.state.subagentRun = { children: [WORKING], receivedAt: Date.now() };
    await animationFrame();
    expect('.mk_subagent_escalation').toHaveCount(0);
});

test('an empty reply is not sent, so Enter on a blank box does nothing', async () => {
    const answers = [];
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        answers.push(args);
        return true;
    });
    await mountCards(makeSession([QUESTION]));
    await click('.mk_subagent_answer_send');
    await animationFrame();
    expect(answers).toEqual([]);
});

test('Enter sends the reply and Shift+Enter writes a new line', async () => {
    const answers = [];
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        answers.push(args);
        return true;
    });
    await mountCards(makeSession([QUESTION]));
    await click('.mk_subagent_answer_input');
    await edit('The last one');
    await animationFrame();
    await press('shift+Enter');
    await animationFrame();
    expect(answers).toEqual([]);
    await press('Enter');
    await animationFrame();
    expect(answers).toEqual([[32, 'The last one']]);
});

test('a failed answer is reported instead of disappearing', async () => {
    const shown = [];
    mockService('notification', {
        add(message) {
            shown.push(String(message));
        },
    });
    onRpc('muk_ai.session', 'answer', () => {
        throw makeServerError({ message: 'Session is not waiting' });
    });
    await mountCards(makeSession([QUESTION]));
    await click('.mk_subagent_option:first-child');
    await animationFrame();
    await animationFrame();
    expect(shown.join(' ')).toInclude('Failed to answer');
});

test('opening a blocked subagent navigates to its own transcript', async () => {
    const session = makeSession([QUESTION]);
    await mountCards(session);
    await click('.mk_subagent_ask_open');
    await animationFrame();
    expect(session.state.subagentOpen.id).toBe(32);
});
