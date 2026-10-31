import {
    advanceTime,
    animationFrame,
    expect,
    press,
    queryAllProperties,
    queryAllTexts,
    test,
} from '@odoo/hoot';
import {
    contains,
    getService,
    mountWebClient,
    MockServer,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';

import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    AISessionModel,
    defineAIModels,
    emit,
    LeadModel,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels(LeadModel);

const APPROVAL = {
    key: 'muk_ai.session:1',
    res_model: 'muk_ai.session',
    res_id: 1,
    session_id: 1,
    label: 'Lead agent',
    sublabel: 'Update 1 Lead record(s)',
    icon: 'back_hand',
    changes: [{ label: 'Name', from: 'Azure', to: 'Azure Interior' }],
    approve: 'approve_tool',
    reject: 'reject_tool',
};

const TASK = {
    key: 'muk_ai.test_lead:2',
    res_model: 'muk_ai.test_lead',
    res_id: 2,
    label: 'Check the offer',
    sublabel: 'Offer review - Globex',
    icon: 'checklist',
    open: 'action_review',
};

function seedChats() {
    AISessionModel._records = [
        {
            id: 1,
            name: 'Unread report',
            state: 'done',
            notification_unread: true,
            last_text: 'The report is **ready**, see [Q1](account.move,4).',
            write_date: '2026-01-01 10:00:00',
        },
        {
            id: 2,
            name: 'Busy chat',
            state: 'running',
            write_date: '2026-01-02 10:00:00',
        },
        {
            id: 3,
            name: 'Of a colleague',
            state: 'done',
            user_id: serverState.publicUserId,
        },
    ];
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 1,
        session_ids: [1],
        space_unread: {},
    }));
}

test('the menu lists the unread chats first, then the recent ones, under the badge and the running mark', async () => {
    seedChats();
    await mountWebClient();
    expect('.mk_systray_btn .o_badge').toHaveText('1');
    expect('.mk_systray_btn .mk_systray_running').toHaveCount(1);
    await contains('.mk_systray_btn').click();
    expect(queryAllTexts('.mk_systray_chats .mk_systray_name')).toEqual([
        'Unread report',
        'Busy chat',
    ]);
    expect('.mk_systray_unread .mk_systray_preview').toHaveText(
        'The report is ready, see Q1.',
    );
    expect('.mk_systray_chats .mk_state_running').toHaveCount(1);
});

test('the badge follows the bus and caps at 99', async () => {
    await mountWebClient();
    for (const [count, badge] of [
        [5, '5'],
        [120, '99+'],
    ]) {
        await emit('muk_ai.notification_badge', { count, session_ids: [] });
        expect('.mk_systray_btn .o_badge').toHaveText(badge);
    }
    await emit('muk_ai.notification_badge', { count: 0, session_ids: [] });
    expect('.mk_systray_btn .o_badge').toHaveCount(0);
});

test('New Chat and a listed chat open in a window, Open Full Chat opens the page', async () => {
    seedChats();
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_row:contains(Busy chat)').click();
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_top .btn-primary').click();
    expect(chat.windowIds).toEqual([2, 4]);
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_top [title="Open Full Chat"]').click();
    await animationFrame();
    expect('.o_action_manager .mk_chat').toHaveCount(1);
});

test('on a record the menu asks about it and runs an offered action in a new window', async () => {
    onRpc('muk_ai.session', 'start', ({ args }) => expect.step(`start ${args[1]}`));
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.act_window',
        res_model: 'muk_ai.test_lead',
        res_id: 2,
        views: [[false, 'form']],
    });
    await contains('.mk_systray_btn').click();
    await animationFrame();
    expect('.mk_systray_ask').toHaveText('Ask about Globex');
    expect(queryAllTexts('.mk_systray_chips .mk_systray_chip')).toEqual(['Pipeline']);
    await contains('.mk_systray_chips .mk_systray_chip').click();
    await animationFrame();
    expect.verifySteps(['start Show my **pipeline**']);
    expect(getService(AIChatPlugin).windowIds).toHaveLength(1);
});

test('the hotkeys start a chat in a window and open the full page', async () => {
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    await press(['alt', 'shift', 'b']);
    await animationFrame();
    expect(chat.windowIds).toEqual([3]);
    await press(['alt', 'shift', 'f']);
    await animationFrame();
    expect('.o_action_manager .mk_chat').toHaveCount(1);
});

test('the list picks up chats created or deleted elsewhere', async () => {
    AISessionModel._records = [];
    await mountWebClient();
    await contains('.mk_systray_btn').click();
    expect('.mk_systray_menu').toHaveText(/No chats yet\./);
    const [id] = MockServer.env['muk_ai.session'].create([
        { name: 'From a cron', state: 'done' },
    ]);
    await emit('muk_ai.session_state', { session_id: id, state: 'done' });
    await advanceTime(500);
    await animationFrame();
    expect(queryAllTexts('.mk_systray_chats .mk_systray_name')).toEqual([
        'From a cron',
    ]);
    await emit('muk_ai.session_state', { session_id: id, deleted: true });
    expect('.mk_systray_menu').toHaveText(/No chats yet\./);
});

test('Needs you lists what waits under an amber mark and decides only a single write in place', async () => {
    let needs = [APPROVAL, TASK];
    onRpc('muk_ai.session', 'get_needs_you', () => needs);
    onRpc('muk_ai.session', 'approve_tool', ({ args }) => {
        expect.step(`approve ${args[0]}`);
        needs = [TASK];
        return {};
    });
    await mountWebClient();
    expect('.mk_systray_btn .mk_systray_needs').toHaveCount(1);
    expect('.mk_systray_btn').toHaveAttribute('title', 'MuK AI - 2 things need you');
    await contains('.mk_systray_btn').click();
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
    expect('.mk_systray_row:contains(Demo)').toHaveCount(0);
    expect('.mk_systray_row:contains(Other)').toHaveCount(1);
    await contains('.mk_systray_need:first .btn-primary', { visible: false }).click();
    expect.verifySteps(['approve 1']);
    expect('.mk_systray_need').toHaveCount(1);
    expect('.mk_systray_row:contains(Demo)').toHaveCount(1);
    expect('.mk_systray_menu').toHaveCount(1);
    needs = [];
    await emit('mail.activity/updated', { activity_deleted: true });
    await advanceTime(300);
    await animationFrame();
    expect('.mk_systray_need').toHaveCount(0);
    expect('.mk_systray_btn .mk_systray_needs').toHaveCount(0);
});

test('a waiting item opens where it lives: a chat in a window, anything else through its action', async () => {
    onRpc('muk_ai.session', 'get_needs_you', () => [APPROVAL, TASK]);
    onRpc('muk_ai.test_lead', 'action_review', ({ args }) => ({
        type: 'ir.actions.act_window',
        res_model: 'muk_ai.test_lead',
        res_id: args[0][0],
        views: [[false, 'form']],
    }));
    await mountWebClient();
    const chat = getService(AIChatPlugin);
    await contains('.mk_systray_btn').click();
    await contains('.mk_systray_row:contains(Lead agent)').click();
    expect(chat.windowIds).toEqual([1]);
    await contains('.mk_systray_btn').click();
    expect('.mk_systray_need:last .mk_systray_decide button').toHaveCount(0);
    await contains('.mk_systray_row:contains(Check the offer)').click();
    await animationFrame();
    expect('.o_form_view .o_field_widget[name=name] input').toHaveValue('Globex');
});

test('a chat starting to wait for its owner is fetched into Needs you', async () => {
    let needs = [];
    onRpc('muk_ai.session', 'get_needs_you', () => {
        expect.step('fetch');
        return needs;
    });
    await mountWebClient();
    expect.verifySteps(['fetch']);
    await emit('muk_ai.session_state', {
        session_id: 1,
        state: 'running',
        awaiting_user: false,
    });
    await advanceTime(300);
    expect.verifySteps([]);
    needs = [APPROVAL];
    await emit('muk_ai.session_state', {
        session_id: 1,
        state: 'waiting',
        awaiting_user: true,
    });
    await advanceTime(300);
    await animationFrame();
    expect.verifySteps(['fetch']);
    expect('.mk_systray_btn .mk_systray_needs').toHaveCount(1);
});
