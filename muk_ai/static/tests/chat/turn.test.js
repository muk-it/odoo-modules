import {
    animationFrame,
    expect,
    queryAllProperties,
    queryAllTexts,
    test,
} from '@odoo/hoot';
import { Component, markRaw, t, useProps, xml } from '@odoo/owl';
import {
    contains,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import { turnBuilders, turnRenderers } from '@muk_ai/core/session/turns';
import {
    defineAIModels,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const ask = (values) => ({ kind: 'ask_user', event_id: 2, sequence: 2, ...values });

async function mountTranscript(events, values = {}, props = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ events, iteration_count: 1, ...values }),
    );
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session, ...props } });
    return session;
}

test('tool calls draw as cards opening on click, a run of them as one group counting its errors', async () => {
    await mountTranscript([
        { kind: 'user_message', content: 'Go', event_id: 1 },
        {
            kind: 'tool_call',
            call_id: 'c1',
            name: 'search_read',
            arguments: '{"model": "res.partner"}',
        },
        { kind: 'tool_result', call_id: 'c1', result: '{"records": []}' },
        { kind: 'tool_call', call_id: 'c2', name: 'create_record', arguments: '{}' },
        { kind: 'tool_result', call_id: 'c2', result: '{"error": "denied"}' },
        { kind: 'text', content: 'Done', event_id: 6 },
        {
            kind: 'tool_call',
            call_id: 'c3',
            name: 'open_record',
            arguments: '{"id": 7}',
        },
        { kind: 'tool_result', call_id: 'c3', result: '{"ok": true}' },
    ]);
    expect('.mk_tool_group .mk_tool_head').toHaveText(/^Used 2 tools/);
    expect(queryAllTexts('.mk_tool_group .mk_tool_chip')).toEqual([
        'Search Partner',
        'create_record',
    ]);
    expect(queryAllTexts('.mk_tool_group .mk_tool_badge')).toEqual(['1', '1']);
    await contains('.mk_tool_group > .mk_tool_head').click();
    expect('.mk_tool_group_body .mk_tool_read + .mk_tool_error').toHaveCount(1);
    await contains('.mk_tool_nav .mk_tool_head').click();
    expect(
        queryAllProperties('.mk_tool_nav .mk_tool_section_label', 'textContent'),
    ).toEqual(['Arguments', 'Result']);
    expect('.mk_tool_nav code:first').toHaveText(/^\{\s+"id": 7\s+\}$/);
    await contains('.mk_tool_nav .mk_tool_head').click();
    expect('.mk_tool_nav .mk_tool_body').toHaveCount(0);
});

test('a tool card names its action, model and outcome in plain words, its arguments on demand', async () => {
    const call = (id, name, args, result) => [
        { kind: 'tool_call', call_id: id, name, arguments: JSON.stringify(args) },
        { kind: 'tool_result', call_id: id, result: JSON.stringify(result) },
    ];
    await mountTranscript([
        { kind: 'user_message', content: 'Go', event_id: 1 },
        ...call('a', 'search_read', { model: 'res.partner' }, [{ id: 1 }, { id: 2 }]),
        ...call(
            'h',
            'search_count',
            { model: 'res.partner', domain: '[]' },
            { count: 22 },
        ),
        ...call('b', 'read_records', { model: 'res.partner', ids: [1, 2, 3] }, [
            { id: 1, display_name: 'Azure' },
            { id: 2, display_name: 'Deco' },
            { id: 3, display_name: 'Wood' },
        ]),
        ...call(
            'c',
            'read_group',
            { model: 'res.partner', groupby: ['country_id:month'] },
            [],
        ),
        ...call(
            'd',
            'update_records',
            { model: 'res.partner', values: { phone: '1', email: 'a' } },
            true,
        ),
        ...call('e', 'web_search', { query: 'odoo crm' }, {}),
        ...call('f', 'web_fetch', { url: 'https://www.odoo.com/page' }, {}),
        ...call('g', 'custom_tool', { secret: 'x' }, {}),
    ]);
    await contains('.mk_tool_group > .mk_tool_head').click();
    await animationFrame();
    expect(
        queryAllTexts('.mk_tool_group_body .mk_tool_head').map((text) =>
            text.replace(/\s+/g, ' '),
        ),
    ).toEqual([
        'Search Partner 2 found',
        'Count Partner 22',
        'Read Partner Azure, Deco +1',
        'Summarize Partner by country_id label',
        'Update Partner phone label, email label',
        'Search the web "odoo crm"',
        'Read a web page www.odoo.com',
        'custom_tool',
    ]);
    expect('.mk_tool_group_body').not.toHaveText(/secret|"model"/);
    await contains('.mk_tool_group_body .mk_tool:last .mk_tool_head').click();
    expect('.mk_tool_group_body .mk_tool:last code:first').toHaveText(/"secret": "x"/);
});

test('a tool card relabels itself once the model names arrive', async () => {
    const { promise, resolve } = Promise.withResolvers();
    onRpc('ir.model', 'ai_tool_labels', async () => {
        await promise;
        return { 'res.users': { name: 'User', fields: {} } };
    });
    await mountTranscript([
        { kind: 'user_message', content: 'Go', event_id: 1 },
        {
            kind: 'tool_call',
            call_id: 'u',
            name: 'search_count',
            arguments: '{"model": "res.users"}',
        },
    ]);
    expect('.mk_tool_name').toHaveText('Count res.users');
    resolve();
    await animationFrame();
    expect('.mk_tool_name').toHaveText('Count User');
});

test('an approval card shows the change, waits for the owner and is decided with its buttons', async () => {
    onRpc('muk_ai.session', 'approve_for_session', () => {
        expect.step('approve_for_session');
        return snapshot({
            state: 'running',
            events: [
                ask({ call_id: 'c1', resolution: 'yesno' }),
                { kind: 'approval', call_id: 'c1', decision: 'approved_session' },
            ],
        });
    });
    const preview = {
        kind: 'update',
        title: 'Update contact',
        model: 'res.partner',
        model_label: 'Contact',
        targets: [{ id: 7, display_name: 'Azure' }],
        changes: [
            { label: 'Name', field: 'name', from: 'Azure', to: 'Azure Interior' },
        ],
    };
    const session = await mountTranscript(
        [ask({ call_id: 'c1', resolution: 'yesno', text: 'Rename it?', preview })],
        { state: 'waiting', pending_ask: { kind: 'approval', call_id: 'c1' } },
    );
    expect('.mk_ask_head').toHaveText(/Confirmation required\s+· Contact/);
    expect('.mk_ask_change .text-decoration-line-through').toHaveText('Azure');
    expect('.mk_ask_change').toHaveText(/Azure Interior$/);
    await contains('.mk_ask_toggle').click();
    expect('.mk_ask_args').toHaveText(/"title": "Update contact"/);
    session.data.can_write = false;
    await animationFrame();
    expect('.mk_ask_card').toHaveText(/Waiting for the owner to answer\.$/);
    session.data.can_write = true;
    await animationFrame();
    expect(queryAllTexts('.mk_ask_actions button')).toEqual([
        'Approve',
        'Allow for session',
        'Reject',
    ]);
    await contains('.mk_ask_actions button:contains(Allow for session)').click();
    expect.verifySteps(['approve_for_session']);
    expect('.mk_ask_card').toHaveText(/Approved for this session\.$/);
});

test('a create approval heads each of several records and lists the new lines', async () => {
    const preview = {
        kind: 'create',
        title: 'New 2 Contact records',
        properties: [
            { label: 'Name', field: 'name', value: 'One', record: 1 },
            { label: 'Email', field: 'email', value: 'one@example.com', record: 1 },
            {
                label: 'Child Contacts',
                field: 'child_ids',
                value: 'Desk, Quantity 5, Price 9',
                lines: [
                    {
                        title: 'Desk',
                        details: [
                            { label: 'Quantity', value: '5' },
                            { label: 'Price', value: '9' },
                        ],
                    },
                ],
                record: 1,
            },
            { label: 'Name', field: 'name', value: 'Two', record: 2 },
        ],
    };
    await mountTranscript(
        [ask({ call_id: 'c1', resolution: 'yesno', text: 'Create them?', preview })],
        { state: 'waiting', pending_ask: { kind: 'approval', call_id: 'c1' } },
    );
    expect(queryAllTexts('.mk_ask_record')).toEqual(['Record 1', 'Record 2']);
    expect(queryAllTexts('.mk_ask_change > span')).toEqual([
        'One',
        'one@example.com',
        'Two',
    ]);
    expect('.mk_ask_line > :first-child').toHaveText('Desk');
    expect(queryAllTexts('.mk_ask_detail')).toEqual(['Quantity 5', 'Price 9']);
});

test('a question offers its options as answers while it waits and the chat is writable', async () => {
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        expect.step(args[1]);
        return snapshot({ state: 'running' });
    });
    const session = await mountTranscript(
        [ask({ call_id: 'c2', text: 'Which stage?', options: ['New', 'Won'] })],
        { state: 'waiting', pending_ask: { kind: 'question', call_id: 'c2' } },
    );
    expect('.mk_ask_simple .mk_bubble_text').toHaveText('Which stage?');
    session.data.can_write = false;
    await animationFrame();
    expect('.mk_ask_options button:disabled').toHaveCount(2);
    session.data.can_write = true;
    await animationFrame();
    await contains('.mk_ask_options button:contains(Won)').click();
    expect.verifySteps(['Won']);
    expect('.mk_ask_options button:disabled').toHaveCount(2);
});

test('messages copy, branch and rewind, the last answer regenerates, a reader only copies', async () => {
    let copied = '';
    patchWithCleanup(navigator.clipboard, {
        writeText: async (text) => (copied = text),
    });
    onRpc('muk_ai.session', 'fork_at_event', ({ args }) => {
        expect.step(`fork ${args[1]}`);
        return 9;
    });
    const session = await mountTranscript(
        [
            { kind: 'user_message', content: 'one', event_id: 1 },
            { kind: 'text', content: 'first', event_id: 2 },
            { kind: 'user_message', content: 'two', event_id: 3 },
            { kind: 'text', content: 'second', event_id: 4 },
        ],
        {},
        { onForked: (id) => expect.step(`opened ${id}`) },
    );
    expect('.mk_msg_fork').toHaveCount(4);
    expect('.mk_msg_undo').toHaveCount(4);
    expect('.mk_turn_assistant:last .mk_msg_regenerate').toHaveCount(1);
    expect('.mk_msg_regenerate').toHaveCount(1);
    await contains('.mk_turn_user:first .mk_msg_copy', { visible: false }).click();
    expect(copied).toBe('one');
    await contains('.mk_turn_assistant:first .mk_msg_fork', { visible: false }).click();
    expect.verifySteps(['fork 2', 'opened 9']);
    session.data.can_write = false;
    await animationFrame();
    expect('.mk_msg_fork, .mk_msg_undo, .mk_msg_regenerate').toHaveCount(0);
    expect('.mk_msg_copy').toHaveCount(4);
});

test('a compaction shows its progress and stop button, its failure, its summary or its cancel', async () => {
    onRpc('muk_ai.session', 'stop_compact', () => {
        expect.step('stop_compact');
        return snapshot({ state: 'compacting' });
    });
    const session = await mountTranscript([], { state: 'compacting' });
    const progress = {
        kind: 'compact_progress',
        event_id: 5,
        message_count: 12,
        tokens_estimate: 3000,
    };
    for (const [values, text] of [
        [
            { state: 'streaming', auto: true },
            'Auto-compacting · 12 msgs · ~3000 tokens Stop Summarizing conversation...',
        ],
        [{ state: 'error', error: 'Model offline' }, 'Compaction failed Model offline'],
        [
            {
                state: 'done',
                original_messages: 12,
                original_tokens: 3000,
                summary: 'Short',
            },
            '/compact · compacted 12 msgs / 3000 tokens Show summary',
        ],
        [{ state: 'cancelled' }, '/compact · cancelled'],
    ]) {
        session.state.events = markRaw([{ ...progress, ...values }]);
        await animationFrame();
        expect(
            queryAllTexts('.mk_turn_compact_progress', {
                inline: true,
            })[0].toLowerCase(),
        ).toBe(text.toLowerCase());
    }
    session.state.events = markRaw([{ ...progress, state: 'streaming' }]);
    await animationFrame();
    await contains('.mk_compact_stop').click();
    expect.verifySteps(['stop_compact']);
});

test('an addon draws the turns of the event kinds it builds', async () => {
    class PlanTurn extends Component {
        static template = xml`<ol class="o_test_plan"><li t-foreach="this.props.turn.steps" t-as="step" t-key="step" t-out="step"/></ol>`;
        props = useProps({ turn: t.object(), session: t.object() });
    }
    turnBuilders.add('plan', (entry) => ({ role: 'plan', steps: entry.steps }));
    turnRenderers.add('plan', PlanTurn);
    await mountTranscript([{ kind: 'plan', steps: ['Read', 'Write'], event_id: 1 }]);
    expect(queryAllTexts('.mk_turn_plan .o_test_plan li')).toEqual(['Read', 'Write']);
});

test('the sources of an answer fold behind a chip, a cited record opens beside the docked chat', async () => {
    const sources = [
        ...Array.from({ length: 9 }, (_, index) => ({
            id: `web:${index}`,
            type: 'web',
            url: `https://${index}.example`,
            domain: `${index}.example`,
        })),
        {
            id: 'record:7',
            type: 'record',
            res_model: 'res.partner',
            res_id: 7,
            display_name: 'Azure',
        },
    ];
    const session = await mountTranscript([
        { kind: 'user_message', content: 'Find', event_id: 1 },
        {
            kind: 'tool_result',
            call_id: 'c1',
            name: 'web_search',
            result: 'ok',
            sources,
        },
        { kind: 'text', content: 'Found', event_id: 3 },
    ]);
    const opened = [];
    patchWithCleanup(getService(ActionPlugin), {
        doAction: (action, options) => opened.push([action, options]),
    });
    expect('.mk_sources_chip .mk_sources_label').toHaveText('10 sources');
    expect('.mk_sources_chip .mk_source_ico').toHaveCount(4);
    expect('.mk_sources_chip .mk_sources_more').toHaveText('+6');
    await contains('.mk_sources_chip').click();
    expect('.mk_source_card').toHaveCount(8);
    await contains('.mk_turn_sources_list .mk_sources_more').click();
    await contains('.mk_source_card:contains(Azure)').click();
    expect(session.chat.windows.map((window) => window.id)).toEqual([1]);
    expect(opened).toEqual([
        [
            {
                type: 'ir.actions.act_window',
                res_model: 'res.partner',
                res_id: 7,
                views: [[false, 'form']],
            },
            { clearBreadcrumbs: true },
        ],
    ]);
});

test('a code block copies its code and an inline image opens in the file viewer', async () => {
    let copied = '';
    patchWithCleanup(navigator.clipboard, {
        writeText: async (text) => (copied = text),
    });
    await mountTranscript([
        { kind: 'user_message', content: 'Show', event_id: 1 },
        {
            kind: 'text',
            content: '```js\nlet a = 1;\n```\n\n![chart](/web/image/5)',
            event_id: 2,
        },
    ]);
    await contains('.mk_code_copy', { visible: false }).click();
    expect(copied).toBe('let a = 1;\n');
    expect('.mk_code_copy').toHaveText('Copied');
    await contains('.mk_md_image').click();
    expect('.o-FileViewer-viewImage').toHaveCount(1);
});
