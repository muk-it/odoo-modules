import { expect, test } from '@odoo/hoot';
import { getService, onRpc } from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';
import { patch } from '@web/core/utils/patch';

import {
    defineAIModels,
    openSession,
    recordDialogs,
    recordNotifications,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const approval = { kind: 'approval', call_id: 'c1' };
const history = [
    { kind: 'user_message', content: 'one', event_id: 1, sequence: 1 },
    { kind: 'text', content: 'answer', event_id: 2, sequence: 2 },
    { kind: 'user_message', content: 'two', event_id: 3, sequence: 3 },
];

test('a pending approval is decided with the method each answer calls', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ state: 'waiting', pending_ask: approval }),
    );
    onRpc('muk_ai.session', '*', ({ method, kwargs }) => {
        if (method.includes('_tool') || method === 'approve_for_session') {
            expect.step(kwargs.reason === undefined ? method : [method, kwargs.reason]);
            return snapshot({ state: 'waiting', pending_ask: approval });
        }
    });
    const session = await openSession(1);
    for (const decision of ['approve', 'session', 'reject']) {
        await session.respondYesno(decision);
    }
    await session.rejectTool('no thanks');
    expect.verifySteps([
        'approve_tool',
        'approve_for_session',
        ['reject_tool', ''],
        ['reject_tool', 'no thanks'],
    ]);
});

test('a yes/no question that is no approval is answered with a message', async () => {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({
            state: 'waiting',
            pending_ask: { kind: 'question', call_id: 'c2', text: 'Sure?' },
        }),
    );
    onRpc('muk_ai.session', 'answer', ({ args }) => {
        expect.step(args[1]);
        return snapshot({ state: 'running' });
    });
    const session = await openSession(1);
    await session.respondYesno('approve');
    expect.verifySteps(['Approve']);
});

test('a failing action reports why and leaves the chat as it was', async () => {
    const notes = await recordNotifications();
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({
            events: history,
            view_context: { kind: 'list', model: 'res.partner' },
        }),
    );
    onRpc('muk_ai.session', '*', ({ method }) => {
        if (!['get_snapshot', 'dismiss_notifications'].includes(method)) {
            throw new Error(`${method} broke`);
        }
    });
    const session = await openSession(1);
    session.data.pending_user_messages = [{ content: 'queued' }];
    for (const [run, prefix] of [
        [() => session.stop(), 'Failed to stop session'],
        [() => session.regenerate(), 'Failed to regenerate'],
        [() => session.unpin(), 'Failed to clear view context'],
        [() => session.clear(), 'Failed to clear session'],
        [() => session.setReasoningEffort('high'), 'Failed to set reasoning effort'],
        [() => session.cancelQueued(0), 'Failed to cancel queued message'],
    ]) {
        notes.length = 0;
        await run();
        expect(notes).toHaveLength(1);
        expect(notes[0].message).toMatch(new RegExp(`^${prefix}: .*broke`));
        expect(notes[0].type).toBe('danger');
    }
    expect(session.data.pending_user_messages).toEqual([{ content: 'queued' }]);
});

test('steering a running chat is refused with a warning', async () => {
    const notes = await recordNotifications();
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ state: 'running', events: history }),
    );
    onRpc('muk_ai.session', '*', ({ method }) => {
        if (!['get_snapshot', 'dismiss_notifications'].includes(method)) {
            expect.step(method);
        }
    });
    const session = await openSession(1);
    for (const run of [
        () => session.clear(),
        () => session.compact(),
        () => session.undoToEvent(3),
        () => session.forkAtEvent(3),
        () => session.openHandoverPicker(),
        () => session.regenerate(),
    ]) {
        await run();
    }
    expect.verifySteps([]);
    expect(notes.map((note) => note.type)).toEqual([
        'warning',
        'warning',
        'warning',
        'warning',
        'warning',
    ]);
});

test('rewinding asks first and cuts the transcript only once confirmed', async () => {
    const dialogs = await recordDialogs();
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ events: history }));
    onRpc('muk_ai.session', 'undo_to_event', ({ args }) => {
        expect.step(`undo ${args[1]}`);
        return snapshot({ events: history.slice(0, 2) });
    });
    const session = await openSession(1);
    for (const [eventId, answer, after] of [
        [1, 'cancel', 2],
        [3, 'confirm', 0],
    ]) {
        const done = session.undoToEvent(eventId);
        expect(dialogs.at(-1).props.body).toInclude(`the ${after} event(s)`);
        dialogs.at(-1).props[answer]();
        await done;
    }
    expect.verifySteps(['undo 3']);
    expect(session.state.events).toHaveLength(2);
});

test('forking announces the new chat, handing over drops the chat everywhere', async () => {
    const dialogs = await recordDialogs();
    onRpc('muk_ai.session', 'get_snapshot', () => snapshot({ events: history }));
    onRpc('muk_ai.session', 'fork_at_event', () => 42);
    onRpc('muk_ai.session', 'action_handover', ({ args }) => {
        expect.step(`handover ${args[1]}`);
        return true;
    });
    const session = await openSession(1);
    const chat = session.chat;
    chat.events.addEventListener('created', ({ detail }) =>
        expect.step(`created ${detail.id} from ${detail.from}`),
    );
    chat.events.addEventListener('session_state', ({ detail }) =>
        expect.step(`deleted ${detail.session_id}`),
    );
    expect(await session.forkAtEvent(3)).toBe(42);
    chat.openWindow(1);
    session.openHandoverPicker('ann');
    expect(dialogs.at(-1).props.domain).toEqual([
        ['share', '=', false],
        ['active', '=', true],
        ['id', '!=', session.data.user_id[0]],
        ['name', 'ilike', 'ann'],
    ]);
    await dialogs.at(-1).props.onSelected([9]);
    expect.verifySteps(['created 42 from 1', 'handover 9', 'deleted 1']);
    expect(chat.windowIds).toEqual([]);
});

test('switching agent writes it and names it, an unknown name is refused', async () => {
    const notes = await recordNotifications();
    onRpc('muk_ai.session', 'write', ({ args }) =>
        expect.step(JSON.stringify(args[1])),
    );
    const session = await openSession(1);
    await session.switchAgent('GENERAL');
    expect(session.agentName).toBe('General');
    await session.setAgent(null);
    expect(session.data.agent_id).toBe(false);
    await session.switchAgent('nobody');
    expect.verifySteps(['{"agent_id":1}', '{"agent_id":false}']);
    expect(notes[0].message).toInclude('No agent matches "nobody"');
});

test('the pinned view opens as a record or a filtered list, docking a full-page chat first', async () => {
    const opened = [];
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ view_context: { kind: 'record', model: 'res.partner', id: 3 } }),
    );
    const session = await openSession(1);
    patch(getService(ActionPlugin), { doAction: (action) => opened.push(action) });
    session.chat.pageSessionId = 1;
    await session.openPinnedContext();
    session.data.view_context = {
        kind: 'list',
        model: 'res.partner',
        view_type: 'kanban',
        domain: [['id', '>', 1]],
    };
    await session.openPinnedContext();
    expect(opened).toEqual([
        {
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            views: [[false, 'form']],
            res_id: 3,
        },
        {
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            views: [[false, 'kanban']],
            domain: [['id', '>', 1]],
        },
    ]);
    expect(session.chat.windowIds).toEqual([1]);
});
