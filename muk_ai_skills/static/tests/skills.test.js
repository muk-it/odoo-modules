import {
    animationFrame,
    describe,
    expect,
    press,
    queryAllProperties,
    queryAllTexts,
    test,
    waitFor,
} from '@odoo/hoot';
import {
    contains,
    getService,
    mountWebClient,
    mountWithCleanup,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';
import { browser } from '@web/core/browser/browser';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import {
    defineAIModels,
    LeadModel,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels(LeadModel);
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

test('the skills menu lists recent skills first, greys out the rest and puts the picked one before the text', async () => {
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
    expect('.mk_skills_panel').toHaveCount(0);
    expect('.mk_composer textarea').toHaveValue('/brief ');
    expect('.mk_composer textarea').toBeFocused();
    expect.verifySteps([]);
    await contains('.mk_composer textarea').edit('/brief for the board', {
        confirm: false,
    });
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['invoke brief for the board']);
    expect(JSON.parse(browser.localStorage.getItem(key))).toEqual(['brief', 'summary']);
    for (const [label, value, steps] of [
        ['Summary', '/summary only the totals', []],
        ['Help', '', ['invoke help only the totals']],
    ]) {
        await contains('.mk_composer textarea').edit('only the totals', {
            confirm: false,
        });
        await contains('.mk_skills_toggle').click();
        await contains(`.mk_skills_panel .mk_skill_label:contains('${label}')`).click();
        await animationFrame();
        expect('.mk_composer textarea').toHaveValue(value);
        expect.verifySteps(steps);
    }
    await contains('.mk_skills_toggle').click();
    await contains('.mk_skills_panel input').press('Escape');
    await animationFrame();
    expect('.mk_skills_panel').toHaveCount(0);
});

test('an empty chat on a record offers the skills of its model, else the agent prompts', async () => {
    const session = await mountChat({
        skills: [
            ...SKILLS,
            skill('enrich', { scope: 'record', models: ['res.partner'] }),
        ],
    });
    expect('.mk_suggestion').toHaveText(/pipeline/i);
    session.data.view_context = { kind: 'record', model: 'res.partner', id: 1 };
    await animationFrame();
    expect('.mk_suggestion').toHaveText(/^enrich\s+Does enrich\.$/i);
    await contains('.mk_suggestion').click();
    expect.verifySteps(['invoke enrich false']);
});

test('on a record the systray offers its skills and opens all of them from its more chip', async () => {
    const enrich = skill('enrich', { scope: 'record', models: ['muk_ai.test_lead'] });
    onRpc('muk_ai.skill', 'fetch_skills', () => [enrich, skill('help')]);
    const answer = (id) => snapshot({ id, skills: [enrich] });
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) => answer(args[0]));
    onRpc('muk_ai.session', 'invoke_skill_from_chat', ({ args }) => {
        expect.step(`invoke ${args[1]}`);
        return answer(args[0]);
    });
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.act_window',
        res_model: 'muk_ai.test_lead',
        res_id: 1,
        views: [[false, 'form']],
    });
    await contains('.mk_systray_btn').click();
    await animationFrame();
    expect(queryAllTexts('.mk_systray_chips .mk_systray_chip')).toEqual(['Enrich']);
    await contains('.mk_systray_chips .mk_systray_chip').click();
    await animationFrame();
    expect.verifySteps(['invoke enrich']);
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_context > div > .mk_systray_chip').click();
    await waitFor('.mk_window .mk_skills_panel input');
});

test('a chat without skills shows no skills button', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ skills: [] }));
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session } });
    expect('.mk_composer textarea').toHaveCount(1);
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
