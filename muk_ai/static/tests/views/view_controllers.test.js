import { describe, expect, test } from '@odoo/hoot';
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/list/list_controller';
import '@muk_ai/views/kanban/kanban_controller';
import '@muk_ai/views/pivot/pivot_controller';
import '@muk_ai/views/graph/graph_controller';

describe.current.tags('muk_ai');
defineMailModels();

class MukAiViewModel extends models.Model {
    _name = 'muk_ai.view_model';
    name = fields.Char();
    amount = fields.Float({ aggregator: 'sum' });
    partner_id = fields.Many2one({ relation: 'res.partner' });
    _records = [
        { id: 1, name: 'A', amount: 10, partner_id: false },
        { id: 2, name: 'B', amount: 20, partner_id: false },
    ];
}
defineModels([MukAiViewModel]);

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
}

test('list controller dispatches a list view_context on mount', async () => {
    const captured = [];
    mockChatWindow(11);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args[1]);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.view_model',
        type: 'list',
        arch: `<list><field name="name"/><field name="amount"/></list>`,
    });
    expect(captured.length).toBeGreaterThan(0);
    expect(captured[0].kind).toBe('list');
    expect(captured[0].model).toBe('muk_ai.view_model');
    expect(captured[0].view_type).toBe('list');
});

test('kanban controller dispatches a kanban view_context', async () => {
    const captured = [];
    mockChatWindow(12);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args[1]);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.view_model',
        type: 'kanban',
        arch: `
            <kanban>
                <templates>
                    <t t-name="card">
                        <field name="name"/>
                    </t>
                </templates>
            </kanban>`,
    });
    expect(captured.length).toBeGreaterThan(0);
    expect(captured[0].view_type).toBe('kanban');
});

test('pivot controller dispatches pivot context with measures + groupbys', async () => {
    const captured = [];
    mockChatWindow(13);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args[1]);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.view_model',
        type: 'pivot',
        arch: `
            <pivot>
                <field name="amount" type="measure"/>
            </pivot>`,
    });
    expect(captured.length).toBeGreaterThan(0);
    expect(captured[0].kind).toBe('pivot');
});

test('graph controller dispatches graph context with mode and measure', async () => {
    const captured = [];
    mockChatWindow(14);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args[1]);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.view_model',
        type: 'graph',
        arch: `
            <graph>
                <field name="partner_id" type="row"/>
                <field name="amount" type="measure"/>
            </graph>`,
    });
    expect(captured.length).toBeGreaterThan(0);
    const graph = captured.find((c) => c.kind === 'graph');
    expect(graph).not.toBe(undefined);
});
