import { animationFrame, expect, queryAllTexts, test } from '@odoo/hoot';
import { Component, t, useProps, xml } from '@odoo/owl';
import {
    contains,
    getService,
    mountWebClient,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { ArtifactsPanel, artifactTypes } from '@muk_ai/chat/artifacts/artifacts';
import {
    defineAIModels,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const sources = [
    {
        id: 'web:1',
        type: 'web',
        url: 'https://a.example',
        domain: 'a.example',
        title: 'Alpha',
    },
    {
        id: 'web:2',
        type: 'web',
        url: 'https://b.example',
        domain: 'b.example',
        title: 'Beta',
    },
];
const events = [
    { kind: 'user_message', content: 'Export', event_id: 1, sequence: 1 },
    { kind: 'tool_call', call_id: 'c1', name: 'export_records', arguments: '{}' },
    {
        kind: 'tool_result',
        call_id: 'c1',
        result: JSON.stringify({ attachment_id: 12, filename: 'deals.xlsx' }),
        sources,
    },
    {
        kind: 'text',
        content: 'Here: ![chart](/web/image/13)',
        event_id: 4,
        sequence: 4,
    },
];

async function mountPanel(values = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ iteration_count: 1, ...values }),
    );
    const session = await openSession(1);
    await mountWithCleanup(ArtifactsPanel, {
        props: { session, onClose: () => expect.step('close') },
    });
    return session;
}

test('files, inline images and sources of a chat gather in tabs, empty tabs are left out', async () => {
    const session = await mountPanel({ events });
    session.state.attachments = [
        { id: 30, filename: 'brief.pdf', mimetype: 'application/pdf' },
    ];
    await animationFrame();
    expect(queryAllTexts('.mk_artifacts_tab')).toEqual(['Attachments', 'Sources']);
    expect('.mk_artifacts_tab.active').toHaveText('Attachments');
    expect('.mk_artifacts_body .mk_att_card').toHaveCount(3);
    expect(queryAllTexts('.mk_artifacts_body .mk_att_card .fw-semibold')).toEqual([
        'brief.pdf',
        'deals.xlsx',
    ]);
    await contains('.mk_artifacts_tab:contains(Sources)').click();
    expect(queryAllTexts('.mk_source_title')).toEqual(['Alpha', 'Beta']);
    await contains('.mk_artifacts_header button').click();
    expect.verifySteps(['close']);
});

test('a chat without artifacts says so, without tabs', async () => {
    await mountPanel();
    expect('.mk_artifacts_tabs').toHaveCount(0);
    expect('.mk_artifacts_body').toHaveText('No artifacts in this conversation yet.');
});

test('an addon adds a tab in its sequence', async () => {
    class PlanTab extends Component {
        static template = xml`<ul class="o_test_plans"><li t-foreach="this.props.items" t-as="item" t-key="item.id" t-out="item.name"/></ul>`;
        props = useProps({
            items: t.array(),
            session: t.object(),
            focusItemId: t.any().optional(),
        });
    }
    artifactTypes.add(
        'plans',
        {
            label: 'Plans',
            icon: 'checklist',
            component: PlanTab,
            collect: () => [{ id: 1, name: 'Roadmap' }],
        },
        { sequence: 15 },
    );
    await mountPanel({ events });
    expect(queryAllTexts('.mk_artifacts_tab')).toEqual([
        'Attachments',
        'Plans',
        'Sources',
    ]);
    await contains('.mk_artifacts_tab:contains(Plans)').click();
    expect('.o_test_plans').toHaveText('Roadmap');
});

test('a chat pointing at an artifact opens the page panel on it', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ iteration_count: 1, events }),
    );
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.client',
        tag: 'muk_ai.chat',
        params: { session_id: 1 },
    });
    expect('.mk_artifacts_panel').toHaveCount(0);
    const session = await openSession(1);
    session.focusArtifact('sources', 'web:2');
    await animationFrame();
    expect('.mk_artifacts_tab.active').toHaveText('Sources');
    expect('.mk_source_card.mk_source_focused').toHaveText(/Beta/);
});
