import { advanceTime, animationFrame, expect, test } from '@odoo/hoot';
import { getService, mountWebClient, onRpc } from '@web/../tests/web_test_helpers';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    defineAIModels,
    emitEvent,
    LeadModel,
    openLeads,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels(LeadModel);

let calls = 0;
let report = null;
let pinned = null;
let pinnedAtSubmit = null;

/**
 * Show the leads in a list under a chat window whose tool results are kept,
 * along with the view context pinned when each result was submitted.
 * @param {object} [options] `openLeads` options
 */
async function openLeadsUnderWindow(options) {
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        pinned = args[1];
    });
    onRpc('muk_ai.session', 'submit_client_result', ({ args }) => {
        pinnedAtSubmit = pinned;
        report.resolve(args[2]);
        return snapshot();
    });
    await mountWebClient();
    await openLeads(options);
    getService(AIChatPlugin).openWindow(1);
    await animationFrame();
}

/**
 * Send an `adjust_search` call to the chat in the window and wait for the
 * report it posts back.
 * @param {object} args the tool arguments
 * @param {Function} [whileRunning] run while the tool waits, e.g. to advance time
 * @returns {Promise<object>} the report
 */
async function adjust(args, whileRunning) {
    report = Promise.withResolvers();
    await emitEvent(1, 'log', {
        kind: 'client_action',
        call_id: `c${++calls}`,
        name: 'adjust_search',
        arguments: JSON.stringify(args),
    });
    await whileRunning?.();
    const result = await report.promise;
    await animationFrame();
    return result;
}

test.tags('desktop');
test('filters, group-bys, searches and a domain land in the search of the list', async () => {
    await openLeadsUnderWindow();
    const result = await adjust({
        filters: ['won'],
        group_bys: ['by_stage'],
        searches: ['name=Glo'],
        custom_domain: '[["amount", ">", 100]]',
    });
    expect(result).toEqual({
        model: 'muk_ai.test_lead',
        view_type: 'list',
        applied: [
            'filter:won',
            'group_by:by_stage',
            'search:name=Glo',
            'domain:[["amount", ">", 100]]',
        ],
        facets: [
            'filter: Won',
            'groupBy: Stage',
            'field: Glo',
            'filter: Amount greater than 100',
        ],
    });
    expect('.o_searchview_facet').toHaveCount(4);
    const again = await adjust({
        custom_domain: '[["amount", ">", 100]]',
        remove_facets: ['Won'],
    });
    expect(again.applied).toEqual([
        'removed:Won',
        'domain:[["amount", ">", 100]] (already active)',
    ]);
    const cleared = await adjust({ remove_facets: ['*'] });
    expect([cleared.applied, cleared.facets]).toEqual([['removed:*'], []]);
});

test('names the view does not know are reported with what it offers', async () => {
    await openLeadsUnderWindow();
    const result = await adjust({
        filters: ['lost'],
        group_bys: ['stage:century', 'nothing'],
        searches: ['bare', 'color=red'],
        remove_facets: ['ghost'],
        custom_domain: 'not json',
        measures: ['amount'],
    });
    expect(result.applied).toEqual([]);
    expect(result.issues).toEqual([
        'No active facet matches "ghost".',
        'Unknown filter "lost".',
        'Unknown group-by interval "century" (year, quarter, month, week or day).',
        'Cannot group by "nothing".',
        'Invalid search "bare" (expected "field=value").',
        'Unknown search field "color".',
        'custom_domain must be a JSON-encoded domain list.',
        'measures, mode, order, stacked and cumulated only apply to pivot or graph views.',
    ]);
    expect(result.available).toEqual({
        facets: [],
        filters: ['won'],
        group_bys: ['by_stage'],
        search_fields: ['name'],
    });
});

test('the view switches first, then a graph takes its measure, mode and order and a pivot its measures, each pinned before the report', async () => {
    await openLeadsUnderWindow();
    const graph = await adjust({
        view_type: 'graph',
        measures: ['amount'],
        mode: 'pie',
        order: 'desc',
        stacked: 0,
    });
    expect(graph.applied).toEqual([
        'view:graph',
        'graph_measure:amount',
        'graph_mode:pie',
        'graph_order:DESC',
        'graph_stacked:false',
    ]);
    expect('.o_graph_view').toHaveCount(1);
    expect([pinnedAtSubmit.graph_measure, pinnedAtSubmit.graph_mode]).toEqual([
        'amount',
        'pie',
    ]);
    const pivot = await adjust({
        view_type: 'pivot',
        group_bys: ['name'],
        measures: ['amount', 'size'],
    });
    expect(pivot.applied).toEqual(['view:pivot', 'group_by:name', 'measure:amount']);
    expect(pivot.issues).toEqual(['Unknown pivot measure "size".']);
    expect('.o_pivot_view th:contains(Amount)').toHaveCount(1);
    expect([pinnedAtSubmit.pivot_row_groupby, pinnedAtSubmit.pivot_measures]).toEqual([
        ['name'],
        ['__count', 'amount'],
    ]);
});

test('a form view under the chat cannot be adjusted', async () => {
    await openLeadsUnderWindow();
    await getService(AIChatPlugin).action.switchView('form', { resId: 1 });
    await animationFrame();
    const result = await adjust({ filters: ['won'] }, () => advanceTime(2100));
    expect(result.note).toInclude('No adjustable view is open in this tab');
});
