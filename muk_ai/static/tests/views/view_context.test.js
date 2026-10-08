import { animationFrame, expect, test } from '@odoo/hoot';
import {
    contains,
    getService,
    mountWebClient,
    onRpc,
    switchView,
    toggleMenuItem,
    toggleSearchBarMenu,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    defineAIModels,
    LeadModel,
    openLeads,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels(LeadModel);

const MODEL = 'muk_ai.test_lead';
const WON = [['stage', '=', 'won']];

function trackPins() {
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => expect.step(args[1]));
}

async function openWindowOverLeads() {
    await mountWebClient();
    getService(AIChatPlugin).openWindow(1);
    await openLeads();
    await animationFrame();
}

test('the chats in a window follow the list, its search and the kanban the user looks at', async () => {
    trackPins();
    await openWindowOverLeads();
    expect.verifySteps([{ kind: 'list', model: MODEL, view_type: 'list' }]);
    await toggleSearchBarMenu();
    await toggleMenuItem('Won');
    expect.verifySteps([
        { kind: 'list', model: MODEL, view_type: 'list', domain: WON },
    ]);
    await switchView('kanban');
    expect.verifySteps([
        { kind: 'list', model: MODEL, view_type: 'kanban', domain: WON },
    ]);
});

test('an opened record pins the record, a new one the model', async () => {
    trackPins();
    await openWindowOverLeads();
    expect.verifySteps([{ kind: 'list', model: MODEL, view_type: 'list' }]);
    await contains('.o_data_row:first .o_data_cell').click();
    expect.verifySteps([{ kind: 'record', model: MODEL, id: 1, display_name: 'Acme' }]);
    await contains('.o_breadcrumb .o_back_button, .o_breadcrumb a').click();
    expect.verifySteps([{ kind: 'list', model: MODEL, view_type: 'list' }]);
    await contains('.o_list_button_add').click();
    expect.verifySteps([{ kind: 'list', model: MODEL, view_type: 'form' }]);
});

test('a pivot and a graph pin their measures and groupings', async () => {
    trackPins();
    await openWindowOverLeads();
    expect.verifySteps([{ kind: 'list', model: MODEL, view_type: 'list' }]);
    await switchView('pivot');
    expect.verifySteps([
        {
            kind: 'pivot',
            model: MODEL,
            view_type: 'pivot',
            pivot_measures: ['__count'],
            pivot_row_groupby: ['stage'],
            pivot_column_groupby: [],
        },
    ]);
    await switchView('graph');
    expect.verifySteps([
        {
            kind: 'graph',
            model: MODEL,
            view_type: 'graph',
            graph_mode: 'bar',
            graph_measure: '__count',
            graph_groupbys: ['stage'],
        },
    ]);
});

test('opening a window pins the view on screen, a view shown in a dialog stays out', async () => {
    trackPins();
    await mountWebClient();
    await openLeads();
    await animationFrame();
    const chat = getService(AIChatPlugin);
    chat.openWindow(1);
    await animationFrame();
    expect.verifySteps([{ kind: 'list', model: MODEL, view_type: 'list' }]);
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.act_window',
        res_model: MODEL,
        views: [[false, 'form']],
        res_id: 2,
        target: 'new',
    });
    expect('.modal .o_form_view').toHaveCount(1);
    expect.verifySteps([]);
    expect(chat.probeContext()).toEqual({
        kind: 'list',
        model: MODEL,
        view_type: 'list',
    });
});
