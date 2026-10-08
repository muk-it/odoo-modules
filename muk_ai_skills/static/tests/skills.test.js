import {
    animationFrame,
    describe,
    expect,
    press,
    queryAllProperties,
    queryAllTexts,
    test,
} from '@odoo/hoot';
import {
    contains,
    mountWithCleanup,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';
import { browser } from '@web/core/browser/browser';

import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import {
    defineAIModels,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();
describe.current.tags('muk_ai_skills');

const skill = (name, values = {}) => ({
    name,
    label: name[0].toUpperCase() + name.slice(1),
    description: `Does ${name}.`,
    icon: 'flash_on',
    scope: 'any',
    models: [],
    requirement: '',
    ...values,
});

const SKILLS = [
    skill('summary'),
    skill('brief'),
    skill('reply', {
        scope: 'chatter',
        requirement: 'needs a record with a chatter open',
    }),
    skill('help'),
];

async function mountChat(values = {}) {
    const answer = () => snapshot({ skills: SKILLS, ...values });
    onRpc('muk_ai.session', 'get_snapshot', answer);
    onRpc('muk_ai.session', 'invoke_skill_from_chat', ({ args, kwargs }) => {
        expect.step(`invoke ${args[1]} ${kwargs.user_input}`);
        return answer();
    });
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session } });
    return session;
}

test('a slash command offers the skills the screen allows and runs one with its text', async () => {
    await mountChat();
    await contains('.mk_composer textarea').edit('/', { confirm: false });
    const names = queryAllTexts('.mk_slash_name');
    expect(names).toInclude('/summary');
    expect(names).not.toInclude('/reply');
    expect(names.filter((name) => name === '/help')).toHaveLength(1);
    await contains('.mk_composer textarea').edit('/summary product xy', {
        confirm: false,
    });
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['invoke summary product xy']);
    expect('.mk_composer textarea').toHaveValue('');
    await contains('.mk_composer textarea').edit('/help', { confirm: false });
    await press('Enter');
    await animationFrame();
    expect.verifySteps([]);
});

test('a pinned record unlocks a chatter skill, a list does not', async () => {
    const session = await mountChat();
    session.state.input = '/re';
    for (const [kind, count] of [
        ['record', 1],
        ['list', 0],
    ]) {
        session.data.view_context = { kind, model: 'res.partner', id: 1 };
        await animationFrame();
        expect(".mk_slash_name:contains('/reply')").toHaveCount(count);
    }
});

test('the skills menu lists recent skills first, greys out the rest and runs the picked one', async () => {
    const key = `muk_ai_skills.recent.${serverState.userId}`;
    browser.localStorage.setItem(key, JSON.stringify(['summary']));
    await mountChat();
    await contains('.mk_skills_toggle').click();
    expect(
        queryAllProperties('.mk_skills_group', 'textContent').map((text) =>
            text.trim(),
        ),
    ).toEqual(['Recently used', 'All skills', 'Once something is open']);
    expect(queryAllTexts('.mk_skills_panel .mk_skill_label')).toEqual([
        'Summary',
        'Brief',
        'Help',
        'Reply',
    ]);
    expect('.mk_skill_locked').toHaveText(/needs a record with a chatter open/);
    await contains('.mk_skills_panel input').edit('bri', { confirm: false });
    expect(queryAllTexts('.mk_skills_panel .mk_skill_label')).toEqual(['Brief']);
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['invoke brief false']);
    expect('.mk_skills_panel').toHaveCount(0);
    expect(JSON.parse(browser.localStorage.getItem(key))).toEqual(['brief', 'summary']);
    await contains('.mk_skills_toggle').click();
    await press('Escape');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(0);
});

test('a chat without skills shows no skills button', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ skills: [] }));
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session } });
    expect('.mk_composer .mk_attach').toHaveCount(1);
    expect('.mk_skills_toggle').toHaveCount(0);
});

test('an invoked skill reads as its label and its resources on the tool card', async () => {
    await mountChat({
        events: [
            { kind: 'user_message', content: 'Go', event_id: 1, sequence: 1 },
            {
                kind: 'tool_call',
                call_id: 'c1',
                name: 'invoke_skill',
                arguments: '{"skill_name": "summary"}',
                event_id: 2,
                sequence: 2,
            },
            {
                kind: 'tool_result',
                call_id: 'c1',
                name: 'invoke_skill',
                result: {
                    label: 'Summary',
                    resources: [{ name: 'guide.txt' }, { name: 'tone.txt' }],
                },
                event_id: 3,
                sequence: 3,
            },
        ],
    });
    expect('.mk_tool_head').toHaveText(/Use the skill Summary/);
    expect('.mk_tool_head').toHaveText(/guide\.txt, tone\.txt/);
});
