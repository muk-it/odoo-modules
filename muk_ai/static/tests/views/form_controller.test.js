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

import '@muk_ai/views/form/form_controller';

describe.current.tags('muk_ai');
defineMailModels();

class FormPartner extends models.Model {
    _name = 'muk_ai.form_partner';
    name = fields.Char();
    _records = [
        { id: 1, name: 'Acme' },
        { id: 2, name: 'Alpha' },
    ];
}
defineModels([FormPartner]);

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

test('form controller dispatches a record view_context on mount', async () => {
    const captured = [];
    mockChatWindow(7);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.form_partner',
        resId: 1,
        type: 'form',
        arch: `<form><field name="name"/></form>`,
    });
    expect(captured.length).toBeGreaterThan(0);
    expect(captured[0][0]).toBe(7);
    expect(captured[0][1].kind).toBe('record');
    expect(captured[0][1].model).toBe('muk_ai.form_partner');
    expect(captured[0][1].id).toBe(1);
});

test('form controller bails when no active session is set', async () => {
    const captured = [];
    mockChatWindow(null);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.form_partner',
        resId: 1,
        type: 'form',
        arch: `<form><field name="name"/></form>`,
    });
    expect(captured).toEqual([]);
});

test('form controller dispatches a list payload while creating a new record', async () => {
    const captured = [];
    mockChatWindow(8);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        captured.push(args);
        return {};
    });
    await mountView({
        resModel: 'muk_ai.form_partner',
        type: 'form',
        arch: `<form><field name="name"/></form>`,
    });
    expect(captured.length).toBeGreaterThan(0);
    expect(captured[0][0]).toBe(8);
    expect(captured[0][1]).toEqual({
        kind: 'list',
        model: 'muk_ai.form_partner',
        view_type: 'form',
    });
});
