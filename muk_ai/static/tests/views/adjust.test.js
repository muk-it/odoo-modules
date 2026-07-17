import { describe, expect, test } from '@odoo/hoot';
import { advanceTime } from '@odoo/hoot-mock';
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { applyAdjustSearch } from '@muk_ai/views/adjust';

import '@muk_ai/views/list/list_controller';
import '@muk_ai/views/graph/graph_controller';

describe.current.tags('muk_ai');
defineMailModels();

class MukAiAdjustModel extends models.Model {
    _name = 'muk_ai.adjust_model';
    name = fields.Char();
    amount = fields.Float({ aggregator: 'sum' });
    date_col = fields.Date();
    partner_id = fields.Many2one({ relation: 'res.partner' });
    _records = [
        { id: 1, name: 'A', amount: 10, date_col: '2026-01-05', partner_id: false },
        { id: 2, name: 'B', amount: 20, date_col: '2026-02-10', partner_id: false },
    ];
}
defineModels([MukAiAdjustModel]);

const SEARCH_ARCH = `
    <search>
        <field name="name"/>
        <filter name="high" string="High" domain="[('amount', '&gt;', 15)]"/>
        <filter name="high_or_a" string="High or A"
            domain="['|', ('amount', '&gt;', 15), ('name', '=', 'A')]"/>
        <filter name="group_partner" string="Partner"
            context="{'group_by': 'partner_id'}"/>
        <filter name="group_date" string="Date"
            context="{'group_by': 'date_col'}"/>
    </search>`;

function mockChatWindow(activeSessionId) {
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return activeSessionId;
        },
        get sessionIds() {
            return activeSessionId ? [activeSessionId] : [];
        },
    });
    onRpc('muk_ai.session', 'set_view_context', () => ({}));
}

async function mountAdjustList() {
    await mountView({
        resModel: 'muk_ai.adjust_model',
        type: 'list',
        arch: `<list><field name="name"/><field name="amount"/></list>`,
        searchViewArch: SEARCH_ARCH,
    });
}

test('applies filters, group bys and field searches to the live view', async () => {
    mockChatWindow(21);
    await mountAdjustList();
    const result = await applyAdjustSearch(
        {
            filters: ['high'],
            group_bys: ['partner_id'],
            searches: ['name=A'],
        },
        {},
    );
    expect(result.model).toBe('muk_ai.adjust_model');
    expect(result.view_type).toBe('list');
    expect(result.applied).toInclude('filter:high');
    expect(result.applied).toInclude('group_by:partner_id');
    expect(result.applied).toInclude('search:name=A');
    expect(result.facets.length).toBeGreaterThan(0);
    expect(result.issues).toBe(undefined);
});

test('reports unknown names with the available alternatives', async () => {
    mockChatWindow(22);
    await mountAdjustList();
    const result = await applyAdjustSearch(
        { filters: ['nope'], group_bys: ['does_not_exist'] },
        {},
    );
    expect(result.applied).toEqual([]);
    expect(result.issues).toHaveLength(2);
    expect(result.issues[0]).toMatch(/Unknown filter "nope"/);
    expect(result.issues[1]).toMatch(/Cannot group by "does_not_exist"/);
    expect(result.available.filters).toInclude('high');
    expect(result.available.group_bys).toInclude('group_partner');
});

test('removes all facets with the wildcard', async () => {
    mockChatWindow(23);
    await mountAdjustList();
    await applyAdjustSearch({ filters: ['high'] }, {});
    const result = await applyAdjustSearch({ remove_facets: ['*'] }, {});
    expect(result.applied).toInclude('removed:*');
    expect(result.facets).toEqual([]);
});

test('removes a facet by its reported label', async () => {
    mockChatWindow(26);
    await mountAdjustList();
    const first = await applyAdjustSearch({ group_bys: ['partner_id'] }, {});
    expect(first.facets).toHaveLength(1);
    const result = await applyAdjustSearch({ remove_facets: [first.facets[0]] }, {});
    expect(result.applied).toHaveLength(1);
    expect(result.facets).toEqual([]);
});

test('reports available facets when removal misses', async () => {
    mockChatWindow(27);
    await mountAdjustList();
    await applyAdjustSearch({ filters: ['high'] }, {});
    const result = await applyAdjustSearch({ remove_facets: ['nope'] }, {});
    expect(result.issues).toHaveLength(1);
    expect(result.available.facets).toHaveLength(1);
});

test('applies a custom domain as a facet', async () => {
    mockChatWindow(24);
    await mountAdjustList();
    const result = await applyAdjustSearch(
        { custom_domain: '[["amount", ">=", 15]]' },
        {},
    );
    expect(result.applied).toHaveLength(1);
    expect(result.facets.length).toBeGreaterThan(0);
});

test('does not stack an already-active custom domain', async () => {
    mockChatWindow(28);
    await mountAdjustList();
    const domain = '[["amount", ">=", 15]]';
    const first = await applyAdjustSearch({ custom_domain: domain }, {});
    expect(first.facets).toHaveLength(1);
    const second = await applyAdjustSearch({ custom_domain: domain }, {});
    expect(second.applied[0]).toMatch(/already active/);
    expect(second.facets).toHaveLength(1);
});

test('still applies a domain contained in an OR branch of the active domain', async () => {
    mockChatWindow(29);
    await mountAdjustList();
    await applyAdjustSearch({ filters: ['high_or_a'] }, {});
    const result = await applyAdjustSearch(
        { custom_domain: '[["amount", ">", 15]]' },
        {},
    );
    expect(result.applied[0]).not.toMatch(/already active/);
    expect(result.facets).toHaveLength(2);
});

test('changes the interval of an already-active date group by', async () => {
    mockChatWindow(30);
    await mountAdjustList();
    const first = await applyAdjustSearch({ group_bys: ['date_col:month'] }, {});
    expect(first.facets[0]).toMatch(/Month/);
    const second = await applyAdjustSearch({ group_bys: ['date_col:year'] }, {});
    expect(second.applied).toInclude('group_by:date_col:year');
    expect(second.facets.join(' ')).toMatch(/Year/);
});

test('rejects an unknown group-by interval', async () => {
    mockChatWindow(31);
    await mountAdjustList();
    const result = await applyAdjustSearch({ group_bys: ['date_col:decade'] }, {});
    expect(result.applied).toEqual([]);
    expect(result.issues[0]).toMatch(/Unknown group-by interval "decade"/);
});

test('reports an issue when the view switch silently fails', async () => {
    mockChatWindow(32);
    await mountAdjustList();
    const env = { services: { action: { switchView: async () => {} } } };
    const result = await applyAdjustSearch(
        { view_type: 'kanban', filters: ['high'] },
        env,
    );
    expect(result.view_type).toBe('list');
    expect(result.applied).toEqual(['filter:high']);
    expect(result.issues[0]).toMatch(/did not switch to "kanban"/);
});

test('updates graph mode, order and measure', async () => {
    mockChatWindow(25);
    await mountView({
        resModel: 'muk_ai.adjust_model',
        type: 'graph',
        arch: `
            <graph>
                <field name="partner_id" type="row"/>
                <field name="amount" type="measure"/>
            </graph>`,
        searchViewArch: SEARCH_ARCH,
    });
    const result = await applyAdjustSearch(
        { mode: 'line', order: 'desc', measures: ['amount'] },
        {},
    );
    expect(result.view_type).toBe('graph');
    expect(result.applied).toInclude('graph_mode:line');
    expect(result.applied).toInclude('graph_order:DESC');
    expect(result.applied).toInclude('graph_measure:amount');
});

test('returns a note when no adjustable view is mounted', async () => {
    const pending = applyAdjustSearch({ filters: ['high'] }, {});
    await advanceTime(2500);
    const result = await pending;
    expect(result.note).toMatch(/No adjustable view is open/);
});
