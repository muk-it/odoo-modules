import {
    animationFrame,
    expect,
    queryAllProperties,
    queryAllTexts,
    runAllTimers,
    test,
} from '@odoo/hoot';
import {
    clickSave,
    contains,
    editAce,
    fields,
    models,
    mountView,
    onRpc,
    preloadBundle,
} from '@web/../tests/web_test_helpers';

import { defineAIModels } from '@muk_ai/../tests/muk_ai_test_helpers';

class AgentModel extends models.Model {
    _name = 'muk_ai.test_agent';
    name = fields.Char();
    config = fields.Json({ string: 'Configuration' });
    tool_names = fields.Json();
    tool_options = fields.Json();
    effort = fields.Selection({
        selection: [
            ['low', 'Low'],
            ['medium', 'Medium'],
            ['high', 'High'],
        ],
    });
    effort_options = fields.Json();
    icon = fields.Char();
    events = fields.Json();
    _records = [
        {
            id: 1,
            name: 'Sales',
            config: { temperature: 0.2 },
            tool_names: ['search_read', 'create_record'],
            tool_options: [
                { name: 'search_read', category: 'read' },
                { name: 'create_record', category: 'write' },
                { name: 'read_group', category: 'read' },
                { name: 'open_record', category: 'nav' },
            ],
            effort: 'low',
            effort_options: ['low', 'high'],
            icon: 'sell',
            events: [
                { kind: 'user_message', content: 'Hello', event_id: 1 },
                {
                    kind: 'tool_result',
                    call_id: 'c1',
                    result: 'ok',
                    sources: [{ id: 'web:1', type: 'web', url: 'https://a.example' }],
                },
                { kind: 'text', content: 'Hi **there**', event_id: 3 },
            ],
        },
    ];
}

defineAIModels(AgentModel);
preloadBundle('web.ace_lib');

function trackWrites() {
    onRpc('muk_ai.test_agent', 'web_save', ({ args }) => expect.step(args[1]));
}

function mountForm(arch) {
    return mountView({
        type: 'form',
        resModel: 'muk_ai.test_agent',
        resId: 1,
        arch: `<form>${arch}</form>`,
    });
}

test('a JSON field is edited as code, saved parsed and refused while it is not JSON', async () => {
    trackWrites();
    await mountForm(
        '<field name="config" widget="json_code" options="{\'mode\': \'json\'}"/>',
    );
    await editAce('{"temperature": ');
    await animationFrame();
    expect('.o_notification').toHaveText(/Invalid JSON in Configuration/);
    expect('.o_field_widget[name=config]').toHaveClass('o_field_invalid');
    expect('.o_form_button_save').toHaveProperty('disabled', true);
    await editAce('{"temperature": 0.7}');
    await clickSave();
    expect.verifySteps([{ config: { temperature: 0.7 } }]);
    expect('.o_field_widget[name=config]').not.toHaveClass('o_field_invalid');
});

test('the tool picker shows the tools as tags coloured by category and adds and removes them', async () => {
    trackWrites();
    await mountForm(
        '<field name="tool_options" invisible="1"/><field name="tool_names" widget="tool_picker" options="{\'options_field\': \'tool_options\'}"/>',
    );
    expect(queryAllTexts('.o_field_widget[name=tool_names] .o_tag')).toEqual([
        'search_read',
        'create_record',
    ]);
    expect(
        queryAllProperties('.o_field_widget[name=tool_names] .o_tag', 'dataset').map(
            (data) => data.color,
        ),
    ).toEqual(['10', '2']);
    await contains('.o_field_widget[name=tool_names] input').edit('re', {
        confirm: false,
    });
    await runAllTimers();
    expect(queryAllTexts('.o-autocomplete--dropdown-item')).toEqual([
        'read_group',
        'open_record',
    ]);
    await contains('.o-autocomplete--dropdown-item:contains(read_group)').click();
    await contains(
        '.o_field_widget[name=tool_names] .o_tag:contains(create_record) .o_delete',
    ).click();
    await contains('.o_field_widget[name=tool_names] input').edit('zzz', {
        confirm: false,
    });
    await runAllTimers();
    expect('.o-autocomplete--dropdown-item').toHaveText('No matching tool');
    await clickSave();
    expect.verifySteps([{ tool_names: ['search_read', 'read_group'] }]);
});

test('a selection only offers the values its sibling field allows', async () => {
    await mountForm(
        '<field name="effort_options" invisible="1"/><field name="effort" widget="filtered_selection" options="{\'options_field\': \'effort_options\'}"/>',
    );
    await contains('.o_field_widget[name=effort] .o_select_menu_toggler').click();
    expect(queryAllTexts('.o_select_menu_item')).toEqual(['Low', 'High']);
});

test('an icon is picked from the searchable grid and shown with its name', async () => {
    trackWrites();
    await mountForm('<field name="icon" widget="icon_selector"/>');
    expect(
        '.o_field_widget[name=icon] .o_select_menu_toggler [data-icon=sell]',
    ).toHaveCount(1);
    await contains('.o_field_widget[name=icon] .o_select_menu_toggler').click();
    await contains('.o_select_menu_searchbox input').edit('rocket', { confirm: false });
    await runAllTimers();
    expect('.o_select_menu_item').toHaveCount(1);
    await contains('.o_select_menu_item').click();
    await clickSave();
    expect.verifySteps([{ icon: 'rocket_launch' }]);
});

test('the events of a session are drawn as its read-only transcript without its sources', async () => {
    await mountForm('<field name="events" widget="ai_session_events" readonly="1"/>');
    expect('.mk_session_events .mk_bubble_user').toHaveText('Hello');
    expect('.mk_session_events .mk_bubble_body strong').toHaveText('there');
    expect('.mk_session_events .mk_msg_copy').toHaveCount(2);
    expect(
        '.mk_session_events .mk_msg_fork, .mk_session_events .mk_sources_chip',
    ).toHaveCount(0);
});
