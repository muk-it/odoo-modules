import {
    animationFrame,
    expect,
    manuallyDispatchProgrammaticEvent,
    press,
    queryAllTexts,
    queryOne,
    test,
    waitFor,
} from '@odoo/hoot';
import { contains, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { ChatComposer } from '@muk_ai/chat/composer/composer';
import {
    defineAIModels,
    openSession,
    pngFile,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const history = [
    { kind: 'user_message', content: 'Question', event_id: 1, sequence: 1 },
];

async function mountComposer(values = {}, props = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ events: history, iteration_count: 1, ...values }),
    );
    onRpc('muk_ai.session', '*', ({ method, args }) => {
        if (
            ['compact', 'clear', 'send_message', 'action_stop', 'write'].includes(
                method,
            )
        ) {
            expect.step(
                method === 'write' ? `write ${JSON.stringify(args[1])}` : method,
            );
            return method === 'write'
                ? true
                : snapshot({ events: history, iteration_count: 1, ...values });
        }
    });
    const session = await openSession(1);
    await mountWithCleanup(ChatComposer, { props: { session, ...props } });
    return session;
}

test('the slash menu filters, walks with the arrows, completes with Tab and clears with Escape', async () => {
    await mountComposer();
    await contains('.mk_composer textarea').edit('/c', { confirm: false });
    expect(queryAllTexts('.mk_slash_name')).toEqual(['/compact', '/clear']);
    expect('.mk_slash_item.active .mk_slash_name').toHaveText('/compact');
    for (const [key, active] of [
        ['ArrowDown', '/clear'],
        ['ArrowDown', '/compact'],
        ['ArrowUp', '/clear'],
    ]) {
        await press(key);
        await animationFrame();
        expect('.mk_slash_item.active .mk_slash_name').toHaveText(active);
    }
    await press('Tab');
    await animationFrame();
    expect('.mk_composer textarea').toHaveValue('/clear');
    await press('Escape');
    await animationFrame();
    expect('.mk_composer textarea').toHaveValue('');
    expect('.mk_slash_menu').toHaveCount(0);
});

test('Enter runs the highlighted command, a destructive one only once it is typed in full', async () => {
    await mountComposer();
    await contains('.mk_composer textarea').edit('/comp', { confirm: false });
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['compact']);
    await contains('.mk_composer textarea').edit('/cle', { confirm: false });
    await press('Enter');
    await animationFrame();
    expect('.mk_composer textarea').toHaveValue('/clear');
    expect.verifySteps([]);
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['clear']);
});

test('typing /agent lists the agents and Enter switches to the chosen one', async () => {
    const session = await mountComposer({ agent_id: [1, 'General'] });
    await session.chat.loadAgents();
    await contains('.mk_composer textarea').edit('/agent ', { confirm: false });
    await animationFrame();
    expect(queryAllTexts('.mk_slash_item', { inline: true })).toEqual([
        'General active',
        'Analyst Analyses',
    ]);
    await contains('.mk_composer textarea').edit('/agent ana', { confirm: false });
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['write {"agent_id":2}']);
    expect('.mk_composer textarea').toHaveValue('');
});

test('Enter sends the message, Shift+Enter starts a new line', async () => {
    await mountComposer();
    await contains('.mk_composer textarea').edit('Hello', { confirm: false });
    await press(['Shift', 'Enter']);
    expect.verifySteps([]);
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['send_message']);
    expect('.mk_composer textarea').toHaveValue('');
});

test('the send button sends, queues or stops with the state of the chat', async () => {
    const session = await mountComposer();
    for (const [state, input, icon, disabled] of [
        ['done', '', 'arrow_upward', true],
        ['done', 'x', 'arrow_upward', false],
        ['running', 'x', 'schedule', false],
        ['running', '', 'stop', false],
    ]) {
        Object.assign(session.data, { state });
        session.state.input = input;
        await animationFrame();
        expect('.mk_send i').toHaveAttribute('data-icon', icon);
        expect('.mk_send').toHaveProperty('disabled', disabled);
    }
    await contains('.mk_send').click();
    expect.verifySteps(['action_stop']);
});

test('the placeholder tells what the chat waits for', async () => {
    const session = await mountComposer({}, { placeholder: 'Ask anything' });
    for (const [values, placeholder] of [
        [{ state: 'done' }, 'Ask anything'],
        [{ state: 'running' }, 'Stop to interrupt...'],
        [
            { state: 'waiting', pending_ask: { kind: 'approval' } },
            'Approve or reject to continue...',
        ],
        [
            { state: 'waiting', pending_ask: { kind: 'question' } },
            'Type your answer...',
        ],
        [{ state: 'waiting_schedule' }, 'Scheduled. Type to wake the agent...'],
    ]) {
        Object.assign(session.data, values);
        await animationFrame();
        expect('.mk_composer textarea').toHaveAttribute('placeholder', placeholder);
    }
});

test('a chat shared with the user shows who owns it instead of the input', async () => {
    await mountComposer({ can_write: false, user_id: [7, 'Marc Demo'] });
    expect('.mk_composer_readonly').toHaveText(
        'Read only: Marc Demo shared this chat with you.',
    );
    expect('.mk_composer').toHaveCount(0);
});

test('picked files are attached as cards that can be removed again', async () => {
    onRpc('muk_ai.session', 'upload_attachments', () => [
        { id: 31, filename: 'shot.png', mimetype: 'image/png' },
    ]);
    onRpc('muk_ai.session', 'discard_attachments', ({ args }) =>
        expect.step(`discard ${args[1]}`),
    );
    await mountComposer();
    const files = new DataTransfer();
    files.items.add(pngFile());
    const input = queryOne('.mk_attach input');
    input.files = files.files;
    await manuallyDispatchProgrammaticEvent(input, 'change');
    await waitFor('.mk_composer .mk_att_card');
    expect('.mk_composer .mk_att_card').toHaveAttribute('title', 'shot.png');
    expect('.mk_send').toHaveProperty('disabled', false);
    await contains('.mk_att_card_remove', { visible: false }).click();
    expect('.mk_att_card').toHaveCount(0);
    expect.verifySteps(['discard 31']);
});

test('a narrow composer keeps the usage ring in its row and the pills in the tools menu', async () => {
    await mountComposer({}, { showMeta: false });
    expect('.mk_composer_meta').toHaveCount(0);
    expect('.mk_composer_usage .mk_usage_meter').toHaveCount(1);
    await contains('.mk_tools_toggle').click();
    expect('.mk_tools_menu [data-pill=approval] .mk_pill').toHaveCount(2);
});
