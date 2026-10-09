import { animationFrame, expect, queryAllTexts, test } from '@odoo/hoot';
import { contains, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { ToolsMenu } from '@muk_ai/chat/tools_menu/tools_menu';
import {
    defineAIModels,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const SOURCES = [
    {
        key: 'web_search',
        section: 'Abilities',
        icon: 'travel_explore',
        label: 'Web search',
        hint: 'Search the web for current information',
        enabled: true,
    },
    {
        key: 'mcp:7',
        section: 'Connectors',
        icon: 'power',
        label: 'EU VAT Info',
        hint: 'eu-vat-info 1.1.0',
        enabled: false,
        items: [
            { label: 'calculate_vat', badge: 'Always allow', tone: 'success' },
            { label: 'validate_vat_number', badge: 'Needs approval', tone: 'warning' },
        ],
    },
];

async function mountMenu(values = {}, props = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot(values));
    const session = await openSession(1);
    await mountWithCleanup(ToolsMenu, { props: { session, ...props } });
    return session;
}

test.tags('desktop');
test('the sources are grouped by section and switch per chat', async () => {
    onRpc('muk_ai.session', 'set_tool_source', ({ args }) => {
        expect.step(`${args[1]} ${args[2]}`);
        return snapshot({
            tool_sources: SOURCES.map((source) => ({ ...source, enabled: true })),
        });
    });
    await mountMenu({ tool_sources: SOURCES });
    await contains('.mk_tools_toggle').click();
    expect(queryAllTexts('.mk_tools_title')).toEqual(['ABILITIES', 'CONNECTORS']);
    expect(queryAllTexts('.mk_tools_label')).toEqual(['Web search', 'EU VAT Info']);
    expect('[data-source=web_search] input').toBeChecked();
    expect('[data-source="mcp:7"] input').not.toBeChecked();
    await contains('[data-source="mcp:7"] input').click();
    expect.verifySteps(['mcp:7 true']);
    expect('[data-source="mcp:7"] input').toBeChecked();
});

test('a connector lists its tools with the permission that applies', async () => {
    await mountMenu({ tool_sources: SOURCES });
    await contains('.mk_tools_toggle').click();
    expect('.mk_tools_items').toHaveCount(0);
    await contains('[data-source="mcp:7"] .mk_tools_expand').click();
    expect(queryAllTexts('.mk_tools_items li', { inline: true })).toEqual([
        'calculate_vat Always allow',
        'validate_vat_number Needs approval',
    ]);
    expect('.mk_tools_items .badge:contains(Needs approval)').toHaveClass(
        'text-bg-warning',
    );
});

test('a narrow surface carries the pills, a shared chat cannot switch anything', async () => {
    onRpc('muk_ai.session', 'set_approval_mode', ({ args }) => {
        expect.step(`approval ${args[1]}`);
        return snapshot();
    });
    const session = await mountMenu({ tool_sources: SOURCES }, { withPills: true });
    await contains('.mk_tools_toggle').click();
    expect(queryAllTexts('.mk_tools_title')).toEqual([
        'ABILITIES',
        'CONNECTORS',
        'APPROVALS',
    ]);
    expect('[data-pill=approval] .mk_pill_ask').toHaveText('Ask first');
    await contains('[data-pill=approval] .mk_pill:contains(Bypass)').click();
    expect.verifySteps(['approval off']);
    session.data.can_write = false;
    await animationFrame();
    expect('.mk_tools_source input:disabled').toHaveCount(2);
    expect('[data-pill=approval] .mk_pill:disabled').toHaveCount(2);
});

test.tags('desktop');
test('without sources and pills the composer shows no tools button', async () => {
    await mountMenu({ tool_sources: [] });
    expect('.mk_tools_toggle').toHaveCount(0);
});

test('the reasoning effort slides through the tiers of the model', async () => {
    onRpc('muk_ai.session', 'set_reasoning_effort', ({ args }) => {
        expect.step(`effort ${args[1]}`);
        return snapshot({
            reasoning_effort_options: ['low', 'high'],
            agent_reasoning_effort: 'low',
            effective_reasoning_effort: 'high',
            override_reasoning_effort: 'high',
        });
    });
    await mountMenu(
        {
            reasoning_effort_options: ['low', 'high'],
            agent_reasoning_effort: 'low',
            effective_reasoning_effort: 'low',
        },
        { withPills: true },
    );
    await contains('.mk_tools_toggle').click();
    expect('[data-pill=effort] .mk_pill').toHaveCount(0);
    expect('[data-pill=effort] .mk_tools_value').toHaveText('Agent default: Low');
    expect('[data-pill=effort] input[type=range]').toHaveAttribute('max', '2');
    await contains('[data-pill=effort] input[type=range]').edit('2');
    expect.verifySteps(['effort high']);
    expect('[data-pill=effort] .mk_tools_value').toHaveText('High');
    expect('[data-pill=effort] .mk_tools_hint').toHaveText(/^Hard analysis/);
});
