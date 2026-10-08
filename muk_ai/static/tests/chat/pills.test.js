import {
    animationFrame,
    expect,
    queryAllProperties,
    queryAllTexts,
    queryOne,
    test,
} from '@odoo/hoot';
import { Component, t, useProps, xml } from '@odoo/owl';
import { contains, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { SessionPills, sessionPills } from '@muk_ai/chat/pills/pills';
import { UsageMeter } from '@muk_ai/chat/usage/usage';
import {
    defineAIModels,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

class Meta extends Component {
    static template = xml`<div><SessionPills session="this.props.session"/><UsageMeter session="this.props.session"/></div>`;
    static components = { SessionPills, UsageMeter };
    props = useProps({ session: t.object() });
}

async function mountMeta(values = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot(values));
    const session = await openSession(1);
    await mountWithCleanup(Meta, { props: { session } });
    return session;
}

const options = () => queryAllTexts('.mk_pill_menu .mk_pill_option', { inline: true });
const checked = () =>
    queryAllTexts('.mk_pill_option:has(.mk_pill_check:not(.invisible)) .fw-semibold');

test('the approval pill shows the mode and where it comes from, and switches it', async () => {
    onRpc('muk_ai.session', 'set_approval_mode', ({ args }) => {
        expect.step(`approval ${args[1]}`);
        return snapshot({
            effective_approval_mode: 'off',
            override_approval_mode: 'off',
        });
    });
    await mountMeta();
    expect('[data-pill=approval]').toHaveAttribute(
        'title',
        'Ask before risky writes (from agent)',
    );
    await contains('[data-pill=approval]').click();
    expect(options()).toEqual([
        'Ask first Ask before risky writes',
        'Bypass Run without asking',
    ]);
    expect(checked()).toEqual(['Ask first']);
    await contains('.mk_pill_option:contains(Run without asking)').click();
    expect.verifySteps(['approval off']);
    expect('[data-pill=approval]').toHaveText('Bypass');
    expect('[data-pill=approval]').toHaveClass(['mk_pill_bypass', 'mk_pill_override']);
    expect('[data-pill=approval]').toHaveAttribute('title', 'Bypass (override)');
});

test('the effort pill offers the tiers of the model and the agent default', async () => {
    onRpc('muk_ai.session', 'set_reasoning_effort', ({ args }) => {
        expect.step(`effort ${args[1]}`);
        return snapshot();
    });
    const session = await mountMeta();
    expect('[data-pill=effort]').toHaveCount(0);
    Object.assign(session.data, {
        reasoning_effort_options: ['low', 'high'],
        agent_reasoning_effort: 'low',
        effective_reasoning_effort: 'low',
    });
    await animationFrame();
    expect('[data-pill=effort]').toHaveText('Low');
    await contains('[data-pill=effort]').click();
    expect(options()).toEqual([
        'Agent default: Low',
        'Low Fastest, everyday questions',
        'High Hard analysis · costs more',
    ]);
    expect(checked()).toEqual(['Agent default: Low']);
    await contains('.mk_pill_option:contains(High)').click();
    expect.verifySteps(['effort high']);
});

test('a shared chat shows its pills without opening them, an addon adds its own', async () => {
    sessionPills.add(
        'voice',
        {
            build: () => ({
                label: 'Voice',
                icon: 'mic',
                options: [{ value: 'on', label: 'On', active: true }],
            }),
            onSelect: (session, value) => expect.step(`voice ${value} ${session.id}`),
        },
        { sequence: 50 },
    );
    const session = await mountMeta();
    expect(queryAllTexts('.mk_pill .mk_pill_label')).toEqual(['Ask', 'Voice']);
    await contains('[data-pill=voice]').click();
    await contains('.mk_pill_option').click();
    expect.verifySteps(['voice on 1']);
    session.data.can_write = false;
    await animationFrame();
    expect('[data-pill=approval]').toHaveAttribute(
        'title',
        'Approvals of a shared chat cannot be changed',
    );
    await contains('[data-pill=approval]').click();
    expect('.mk_pill_menu').toHaveCount(0);
});

test('the usage ring fills with the context window and lists the usage of the turn and the chat', async () => {
    const session = await mountMeta({
        context_window: 8000,
        total_input_tokens: 12000,
        total_output_tokens: 900,
        iteration_count: 4,
        total_cost: 0.4567,
        turn_usage: {
            input_tokens: 6000,
            output_tokens: 300,
            iterations: 2,
            cost: 0.12,
        },
    });
    for (const [tokens, label, level] of [
        [0, '0%', null],
        [6000, '75%', 'mk_usage_amber'],
        [7300, '91%', 'mk_usage_red'],
        [9000, '100%', 'mk_usage_red'],
    ]) {
        session.data.last_input_tokens = tokens;
        await animationFrame();
        expect('.mk_usage_meter').toHaveText(label);
        expect('.mk_usage_meter').toHaveClass(level ? [level] : []);
    }
    session.data.last_input_tokens = 6000;
    await contains('.mk_usage_meter').click();
    expect('.mk_usage_pop').toHaveText(/^Context 6,000 \/ 8,000 tokens \(75%\)/, {
        inline: true,
    });
    const note = queryOne('.mk_usage_note');
    expect(note).toHaveText('At 80% the conversation is compacted automatically');
    expect(note.scrollWidth).toBeLessThan(note.clientWidth + 1);
    const lines = document.createRange();
    lines.selectNodeContents(note);
    expect(lines.getClientRects()).toHaveLength(1);
    expect(queryAllProperties('.mk_usage_grid > span', 'textContent')).toEqual([
        '',
        'Last turn',
        'Session',
        'Input',
        '6,000',
        '12,000',
        'Output',
        '300',
        '900',
        'Iterations',
        '2',
        '4',
        'Cost',
        '$0.120',
        '$0.457',
    ]);
});
