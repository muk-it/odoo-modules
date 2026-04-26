import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    defineModels,
    fields,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_ai/views/fields/session_log/session_log';

describe.current.tags('muk_ai');
defineMailModels();


class MukAiLogModel extends models.Model {
    _name = 'muk_ai.log_model';
    tool_log = fields.Json();
    _records = [{
        id: 1,
        tool_log: [
            { kind: 'tool_call', name: 'search_read', call_id: 'c1', arguments: {} },
            { kind: 'tool_result', call_id: 'c1', result: '{"ok": true}' },
        ],
    }, {
        id: 2, tool_log: false,
    }];
}
defineModels([MukAiLogModel]);


test('SessionLogField renders user + assistant turns from the log', async () => {
    await mountView({
        resModel: 'muk_ai.log_model',
        resId: 1,
        type: 'form',
        arch: `<form><field name="tool_log" widget="ai_session_log"/></form>`,
    });
    expect('.mk_tool').toHaveCount(1);
    expect(queryFirst('.mk_tool_name').textContent).toBe('search_read');
});


test('SessionLogField renders nothing for empty logs', async () => {
    await mountView({
        resModel: 'muk_ai.log_model',
        resId: 2,
        type: 'form',
        arch: `<form><field name="tool_log" widget="ai_session_log"/></form>`,
    });
    expect('.mk_tool').toHaveCount(0);
});


test('SessionLogField expands a tool card on click', async () => {
    await mountView({
        resModel: 'muk_ai.log_model',
        resId: 1,
        type: 'form',
        arch: `<form><field name="tool_log" widget="ai_session_log"/></form>`,
    });
    const card = queryFirst('.mk_tool');
    expect(card.getAttribute('data-expanded')).toBe('0');
    await click('.mk_tool_head');
    await animationFrame();
    expect(queryFirst('.mk_tool').getAttribute('data-expanded')).toBe('1');
});
