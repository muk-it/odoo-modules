import { describe, expect, test } from '@odoo/hoot';
import { queryAll, queryAllTexts } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    defineModels,
    fields,
    mockService,
    models,
    mountView,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { SessionEventsField } from '@muk_ai/views/fields/session_events/session_events';

describe.current.tags('muk_ai');
defineMailModels();

const LOG = [
    { event_id: 1, kind: 'user_message', content: 'list my partners', attachments: [] },
    {
        event_id: 2,
        kind: 'tool_call',
        call_id: 'c1',
        name: 'search',
        arguments: '{"model": "res.partner"}',
    },
    { event_id: 3, kind: 'tool_result', call_id: 'c1', result: '[]' },
    { event_id: 4, kind: 'text', content: 'Found **no** partner.' },
    {
        event_id: 5,
        kind: 'ask_user',
        call_id: 'a1',
        text: 'Delete the empty ones?',
        resolution: 'yesno',
        preview: { kind: 'unlink', model: 'res.partner', arguments: { ids: [1] } },
    },
];

class SessionStub extends models.Model {
    _name = 'muk_ai.session_events_stub';
    name = fields.Char();
    log = fields.Json();
    _records = [
        { id: 1, name: 'Full', log: LOG },
        { id: 2, name: 'Empty', log: [] },
        { id: 3, name: 'Broken', log: false },
    ];
}
defineModels([SessionStub]);

const ARCH = `<form><field name="log" widget="ai_session_events"/></form>`;

/**
 * Mount the stub form and return the mounted field component.
 * @param {number} resId record to open
 * @returns {Promise<object>} the SessionEventsField instance
 */
async function mountField(resId) {
    let instance = null;
    patchWithCleanup(SessionEventsField.prototype, {
        setup() {
            super.setup();
            instance = this;
        },
    });
    await mountView({
        resModel: 'muk_ai.session_events_stub',
        resId,
        type: 'form',
        arch: ARCH,
    });
    await animationFrame();
    return instance;
}

test('the field renders the whole transcript of a session log', async () => {
    const field = await mountField(1);
    expect(field.turns).toHaveLength(2);
    expect(field.turns[0].role).toBe('user');
    expect(field.turns[1].role).toBe('assistant');
    expect(queryAllTexts('.mk_bubble_body').join(' ')).toMatch(/no partner/);
    expect(queryAll('.mk_bubble_body strong').length).toBeGreaterThan(0);
});

test('an empty or missing log renders no turn at all', async () => {
    const empty = await mountField(2);
    expect(empty.turns).toEqual([]);
    const broken = await mountField(3);
    expect(broken.turns).toEqual([]);
});

test('tool cards expand and collapse per call id', async () => {
    const field = await mountField(1);
    expect(field.isToolExpanded('c1')).toBe(false);
    field.toggleToolBlock('c1');
    expect(field.isToolExpanded('c1')).toBe(true);
    expect(field.isToolExpanded('other')).toBe(false);
    field.toggleToolBlock('c1');
    expect(field.isToolExpanded('c1')).toBe(false);
});

test('a resolved tool stays visible even when the turn carries an ask', async () => {
    const field = await mountField(1);
    const turn = { blocks: [{ type: 'ask', callId: 'c1' }] };
    expect(field.isToolHiddenForAsk({ callId: 'c1', result: '[]' }, turn)).toBe(false);
    expect(field.isToolHiddenForAsk({ callId: 'c1', result: null }, turn)).toBe(true);
    expect(field.isToolHiddenForAsk({ callId: 'c2', result: null }, turn)).toBe(false);
});

test('the first click on an ask block really switches to the technical view', async () => {
    const field = await mountField(1);
    const block = field.turns[1].blocks.find((b) => b.type === 'ask');
    expect(block.callId).toBe('a1');
    expect(field.askViewMode(block)).toBe('human');
    field.toggleAskView('a1');
    expect(field.askViewMode(block)).toBe('technical');
    expect(field.askArgsText(block)).toMatch(/"ids"/);
    field.toggleAskView('a1');
    expect(field.askViewMode(block)).toBe('human');
});

test('copying a message reports success through the notification service', async () => {
    const messages = [];
    mockService('notification', { add: (msg) => messages.push(String(msg)) });
    const original = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: () => Promise.resolve() },
    });
    try {
        const field = await mountField(1);
        field.session.copyText('hello');
        await animationFrame();
        expect(messages.some((m) => /Copied to clipboard/.test(m))).toBe(true);
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: original,
        });
    }
});

test('a rejected clipboard write reports the failure', async () => {
    const messages = [];
    mockService('notification', { add: (msg) => messages.push(String(msg)) });
    const original = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: () => Promise.reject(new Error('denied')) },
    });
    try {
        const field = await mountField(1);
        field.copyText('hello');
        await animationFrame();
        expect(messages.some((m) => /Copy failed/.test(m))).toBe(true);
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: original,
        });
    }
});

test('copying nothing never touches the clipboard', async () => {
    mockService('notification', { add: () => {} });
    const writes = [];
    const original = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
            writeText: (t) => {
                writes.push(t);
                return Promise.resolve();
            },
        },
    });
    try {
        const field = await mountField(1);
        field.copyText('');
        field.copyText(null);
        expect(writes).toEqual([]);
    } finally {
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: original,
        });
    }
});
