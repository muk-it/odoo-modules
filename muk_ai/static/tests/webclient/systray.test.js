import { describe, expect, test } from '@odoo/hoot';
import {
    advanceTime,
    animationFrame,
    queryAllProperties,
    queryAllTexts,
} from '@odoo/hoot-dom';
import {
    contains,
    mockService,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

describe.current.tags('muk_ai');
defineMailModels();

const CHATS = [
    {
        id: 1,
        name: 'Unread report',
        state: 'done',
        agent_id: [3, 'Lead agent'],
        last_text: 'The report is **ready**, see [Q1](account.move,4).',
        write_date: '2026-01-01 10:00:00',
    },
    { id: 2, name: 'Busy chat', state: 'running', agent_id: false },
    { id: 4, name: 'Broken', state: 'error', error_message: 'Quota exceeded' },
];

const APPROVAL = {
    key: 'muk_ai.session:1',
    res_model: 'muk_ai.session',
    res_id: 1,
    session_id: 1,
    agent_id: 3,
    label: 'Lead agent',
    sublabel: 'Update Azure',
    icon: 'back_hand',
    changes: [{ label: 'Name', from: 'Azure', to: 'Azure Interior' }],
    approve: 'approve_tool',
    reject: 'reject_tool',
};

const TASK = {
    key: 'project.task:2',
    res_model: 'project.task',
    res_id: 2,
    label: 'Check the offer',
    sublabel: 'Offer review - Globex',
    icon: 'checklist',
    open: 'action_review',
};

function setup({ chats = CHATS, unread = [1], needs = () => [] } = {}) {
    const windows = [];
    const actions = [];
    const handlers = new Map();
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => windows.push(id),
        close: () => {},
        get sessionIds() {
            return [];
        },
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe: (name, cb) => handlers.set(name, cb),
        unsubscribe: (name) => handlers.delete(name),
    });
    mockService('action', {
        currentController: null,
        doAction: (action) => actions.push(action),
    });
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) =>
        JSON.stringify(kwargs.domain).includes('notification_unread')
            ? chats.filter((chat) => unread.includes(chat.id))
            : chats,
    );
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: unread.length,
        session_ids: unread,
    }));
    onRpc('muk_ai.session', 'get_needs_you', () => needs());
    onRpc('muk_ai.agent', 'search_read', () => [
        { id: 3, suggestions: [{ label: 'Pipeline', prompt: 'Show my **pipeline**' }] },
    ]);
    const emit = (name, payload) => handlers.get(name)?.(payload);
    return { windows, actions, emit };
}

test('the menu lists the unread chats first with a preview of their last answer', async () => {
    setup();
    await mountWithCleanup(MukAISystray);
    expect('.mk_systray_count').toHaveText('1');
    expect('.mk_systray_icon_wrap.mk_systray_running').toHaveCount(1);
    await contains('.mk_ai_systray_btn').click();
    expect(queryAllTexts('.mk_systray_chats .mk_systray_name')).toEqual([
        'Unread report',
        'Busy chat',
        'Broken',
    ]);
    expect('.mk_systray_unread .mk_systray_preview').toHaveText(
        'The report is ready, see Q1.',
    );
    expect('.mk_systray_row:contains(Busy chat) .mk_systray_preview').toHaveText(
        'Working...',
    );
    expect('.mk_systray_row:contains(Broken) .mk_systray_tag_error').toHaveText(
        'Error',
    );
    expect('.mk_systray_row:contains(Broken) .mk_systray_preview').toHaveText(
        /Quota exceeded$/,
    );
    expect('.mk_systray_chats .mk_state_running').toHaveCount(1);
});

test('the badge caps at 99 and Mark all as read dismisses the unread chats', async () => {
    const unread = Array.from({ length: 120 }, (_, index) => index + 10);
    onRpc('muk_ai.session', 'dismiss_notifications', ({ args }) => {
        expect.step(`dismiss ${args[0].length}`);
        return true;
    });
    setup({ unread });
    await mountWithCleanup(MukAISystray);
    expect('.mk_systray_count').toHaveText('99+');
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_mark_read').click();
    expect.verifySteps(['dismiss 120']);
});

test('New Chat and a listed chat open in a window, Open Full Chat opens the page', async () => {
    onRpc('muk_ai.session', 'create', ({ args }) => {
        expect.step(args[0][0].name);
        return [9];
    });
    const { windows, actions } = setup();
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_row:contains(Busy chat)').click();
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_top .btn-primary').click();
    expect.verifySteps(['New Chat']);
    expect(windows).toEqual([2, 9]);
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_top [title="Open Full Chat"]').click();
    expect(actions.map((action) => action.tag)).toEqual(['muk_ai.chat']);
});

test('on a record the menu asks about it and runs an offered action in a new window', async () => {
    onRpc('res.partner', 'read', () => [{ id: 7, display_name: 'Globex' }]);
    onRpc('muk_ai.session', 'create', () => [9]);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        expect.step(`context ${args[1].model} ${args[1].id}`);
        return true;
    });
    onRpc('muk_ai.session', 'start', ({ args }) => {
        expect.step(`start ${args[1]}`);
        return {};
    });
    const { windows } = setup();
    mockService('action', {
        currentController: { props: { resModel: 'res.partner', resId: 7 } },
    });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await animationFrame();
    expect('.mk_systray_ask').toHaveText('Ask about Globex');
    expect(queryAllTexts('.mk_systray_chips .mk_systray_chip')).toEqual(['Pipeline']);
    await contains('.mk_systray_chips .mk_systray_chip').click();
    await animationFrame();
    expect.verifySteps(['context res.partner 7', 'start Show my **pipeline**']);
    expect(windows).toEqual([9]);
});

test('Needs you lists what waits under an amber mark and decides only a single write in place', async () => {
    let needs = [APPROVAL, TASK];
    onRpc('muk_ai.session', 'approve_tool', ({ args }) => {
        expect.step(`approve ${args[0]}`);
        needs = [TASK];
        return {};
    });
    const { emit } = setup({ needs: () => needs });
    await mountWithCleanup(MukAISystray);
    expect('.mk_systray_needs').toHaveCount(1);
    expect('.mk_ai_systray_btn').toHaveAttribute('title', 'MuK AI - 2 things need you');
    await contains('.mk_ai_systray_btn').click();
    expect('.mk_systray_needs_count').toHaveText('2');
    expect(queryAllTexts('.mk_systray_need .mk_systray_name')).toEqual([
        'Lead agent',
        'Check the offer',
    ]);
    expect('.mk_systray_need:first small').toHaveText(/Name Azure\s+Azure Interior$/);
    expect('.mk_systray_need:last small').toHaveText('Offer review - Globex');
    expect(queryAllProperties('.mk_systray_decide button', 'title')).toEqual([
        'Approve',
        'Reject',
    ]);
    expect('.mk_systray_chats .mk_systray_row:contains(Unread report)').toHaveCount(0);
    await contains('.mk_systray_need:first .btn-primary', { visible: false }).click();
    expect.verifySteps(['approve 1']);
    expect('.mk_systray_need').toHaveCount(1);
    expect('.mk_systray_chats .mk_systray_row:contains(Unread report)').toHaveCount(1);
    needs = [];
    emit('mail.activity/updated', { activity_deleted: true });
    await advanceTime(300);
    await animationFrame();
    expect('.mk_systray_need').toHaveCount(0);
    expect('.mk_systray_needs').toHaveCount(0);
});

test('a waiting item opens where it lives: a chat in a window, anything else through its action', async () => {
    onRpc('project.task', 'action_review', ({ args }) => ({
        type: 'ir.actions.act_window',
        res_model: 'project.task',
        res_id: args[0][0],
    }));
    const { windows, actions } = setup({ needs: () => [APPROVAL, TASK] });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_row:contains(Lead agent)').click();
    expect(windows).toEqual([1]);
    await contains('.mk_ai_systray_btn').click();
    expect('.mk_systray_need:last .mk_systray_decide button').toHaveCount(0);
    await contains('.mk_systray_row:contains(Check the offer)').click();
    await animationFrame();
    expect(actions.map((action) => action.res_id)).toEqual([2]);
});

test('a chat starting to wait for its owner is fetched into Needs you', async () => {
    let needs = [];
    const { emit } = setup({
        needs: () => {
            expect.step('fetch');
            return needs;
        },
    });
    await mountWithCleanup(MukAISystray);
    expect.verifySteps(['fetch']);
    emit('muk_ai.session_state', {
        session_id: 1,
        state: 'running',
        awaiting_user: false,
    });
    await advanceTime(300);
    expect.verifySteps([]);
    needs = [APPROVAL];
    emit('muk_ai.session_state', {
        session_id: 1,
        state: 'waiting',
        awaiting_user: true,
    });
    await advanceTime(300);
    await animationFrame();
    expect.verifySteps(['fetch']);
    expect('.mk_systray_needs').toHaveCount(1);
});

test('the list follows chats renamed, created or deleted elsewhere', async () => {
    const { emit } = setup({ chats: [CHATS[0]] });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    emit('muk_ai.session_state', { session_id: 1, state: 'running', name: 'Renamed' });
    await animationFrame();
    expect(queryAllTexts('.mk_systray_chats .mk_systray_name')).toEqual(['Renamed']);
    emit('muk_ai.session_state', { session_id: 1, deleted: true });
    await animationFrame();
    expect('.mk_systray_menu').toHaveText(/No chats yet\./);
});
