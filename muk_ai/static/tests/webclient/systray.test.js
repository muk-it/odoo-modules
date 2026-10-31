import {
    advanceTime,
    animationFrame,
    describe,
    expect,
    queryAllProperties,
    queryAllTexts,
    test,
} from '@odoo/hoot';
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
    key: 'res.partner:2',
    res_model: 'res.partner',
    res_id: 2,
    label: 'Check the offer',
    sublabel: 'Offer review - Globex',
    icon: 'fa-check-square-o',
    open: 'action_review',
};

/**
 * Mock the services the systray talks to and serve the chats it lists.
 * @param {object} [options] `chats`, `needs` (a function), `controller`
 * @returns {object} the windows opened, the actions run and a bus emitter
 */
function setup({ chats = [], needs = () => [], controller = null } = {}) {
    const seen = { opened: [], actions: [] };
    const handlers = {};
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: (id) => seen.opened.push(id),
        close: () => {},
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe: (name, handler) => (handlers[name] = handler),
        unsubscribe: () => {},
    });
    mockService('action', {
        currentController: controller,
        doAction: (action) => seen.actions.push(action),
    });
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) =>
        kwargs.domain.some((leaf) => leaf[0] === 'notification_unread')
            ? chats.filter((chat) => chat.unread)
            : chats,
    );
    onRpc('muk_ai.session', 'get_needs_you', () => needs());
    onRpc('muk_ai.agent', 'search_read', () => [
        { id: 3, suggestions: [{ label: 'Pipeline', prompt: 'Show my **pipeline**' }] },
    ]);
    seen.emit = (name, payload) => handlers[name]?.(payload);
    return seen;
}

test('the menu lists the unread chats first with a preview of their last answer', async () => {
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 1,
        session_ids: [1],
    }));
    setup({
        chats: [
            { id: 2, name: 'Busy chat', state: 'running', agent_id: [3, 'A'] },
            {
                id: 1,
                name: 'Unread report',
                state: 'done',
                unread: true,
                agent_id: [3, 'A'],
                last_text: 'The report is **ready**, see [Q1](account.move,4).',
                write_date: '2026-01-01 10:00:00',
            },
        ],
    });
    await mountWithCleanup(MukAISystray);
    expect('.mk_systray_count').toHaveText('1');
    expect('.mk_systray_icon_wrap.mk_systray_running').toHaveCount(1);
    await contains('.mk_ai_systray_btn').click();
    expect(queryAllTexts('.mk_systray_chats .mk_systray_name')).toEqual([
        'Unread report',
        'Busy chat',
    ]);
    expect('.mk_systray_unread .mk_systray_preview').toHaveText(
        'The report is ready, see Q1.',
    );
    expect('.mk_systray_chats .mk_state_running').toHaveCount(1);
});

test('New Chat and a listed chat open in a window, Open Full Chat opens the page', async () => {
    onRpc('muk_ai.session', 'create', ({ args }) => {
        expect.step(args[0][0].name);
        return [9];
    });
    const seen = setup({
        chats: [{ id: 2, name: 'Busy chat', state: 'done', agent_id: false }],
    });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_row:contains(Busy chat)').click();
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_top .btn-primary').click();
    expect.verifySteps(['New Chat']);
    expect(seen.opened).toEqual([2, 9]);
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_top [title="Open Full Chat"]').click();
    expect(seen.actions.map((action) => action.tag)).toEqual(['muk_ai.chat']);
});

test('on a record the menu asks about it and runs an offered action in a new window', async () => {
    onRpc('res.partner', 'read', () => [{ id: 2, display_name: 'Globex' }]);
    onRpc('muk_ai.session', 'create', () => [9]);
    onRpc('muk_ai.session', 'set_view_context', ({ args }) => {
        expect.step(`context ${args[1].model}`);
        return true;
    });
    onRpc('muk_ai.session', 'start', ({ args }) => {
        expect.step(`start ${args[1]}`);
        return {};
    });
    const seen = setup({
        controller: { props: { resModel: 'res.partner', resId: 2 } },
    });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await animationFrame();
    expect('.mk_systray_ask').toHaveText('Ask about Globex');
    expect(queryAllTexts('.mk_systray_chips .mk_systray_chip')).toEqual(['Pipeline']);
    await contains('.mk_systray_chips .mk_systray_chip').click();
    await animationFrame();
    expect.verifySteps(['context res.partner', 'start Show my **pipeline**']);
    expect(seen.opened).toEqual([9]);
});

test('Needs you lists what waits under an amber mark and decides only a single write in place', async () => {
    let needs = [APPROVAL, TASK];
    onRpc('muk_ai.session', 'approve_tool', ({ args }) => {
        expect.step(`approve ${args[0]}`);
        needs = [TASK];
        return {};
    });
    const seen = setup({
        chats: [
            { id: 1, name: 'Demo', state: 'waiting', agent_id: false },
            { id: 4, name: 'Other', state: 'done', agent_id: false },
        ],
        needs: () => needs,
    });
    await mountWithCleanup(MukAISystray);
    expect('.mk_ai_systray_btn .mk_systray_needs').toHaveCount(1);
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
    expect('.mk_systray_row:contains(Demo)').toHaveCount(0);
    expect('.mk_systray_row:contains(Other)').toHaveCount(1);
    await contains('.mk_systray_need:first .btn-primary', { visible: false }).click();
    expect.verifySteps(['approve 1']);
    expect('.mk_systray_need').toHaveCount(1);
    expect('.mk_systray_row:contains(Demo)').toHaveCount(1);
    needs = [];
    seen.emit('mail.activity/updated', { activity_deleted: true });
    await advanceTime(300);
    await animationFrame();
    expect('.mk_systray_need').toHaveCount(0);
    expect('.mk_ai_systray_btn .mk_systray_needs').toHaveCount(0);
});

test('a waiting item opens where it lives: a chat in a window, anything else through its action', async () => {
    onRpc('res.partner', 'action_review', ({ args }) => ({
        type: 'ir.actions.act_window',
        res_model: 'res.partner',
        res_id: args[0][0],
    }));
    const seen = setup({ needs: () => [APPROVAL, TASK] });
    await mountWithCleanup(MukAISystray);
    await contains('.mk_ai_systray_btn').click();
    await contains('.mk_systray_row:contains(Lead agent)').click();
    expect(seen.opened).toEqual([1]);
    await contains('.mk_ai_systray_btn').click();
    expect('.mk_systray_need:last .mk_systray_decide button').toHaveCount(0);
    await contains('.mk_systray_row:contains(Check the offer)').click();
    await animationFrame();
    expect(seen.actions.map((action) => action.res_id)).toEqual([2]);
});

test('a chat starting to wait for its owner is fetched into Needs you', async () => {
    let needs = [];
    const seen = setup({
        needs: () => {
            expect.step('fetch');
            return needs;
        },
    });
    await mountWithCleanup(MukAISystray);
    expect.verifySteps(['fetch']);
    seen.emit('muk_ai.session_state', {
        session_id: 1,
        state: 'running',
        awaiting_user: false,
    });
    await advanceTime(300);
    expect.verifySteps([]);
    needs = [APPROVAL];
    seen.emit('muk_ai.session_state', {
        session_id: 1,
        state: 'waiting',
        awaiting_user: true,
    });
    await advanceTime(300);
    await animationFrame();
    expect.verifySteps(['fetch']);
    expect('.mk_ai_systray_btn .mk_systray_needs').toHaveCount(1);
});

test('the list picks up chats created or deleted elsewhere', async () => {
    const chats = [];
    const seen = setup({ chats });
    await mountWithCleanup(MukAISystray);
    chats.push({ id: 5, name: 'From a cron', state: 'done', agent_id: false });
    seen.emit('muk_ai.session_state', { session_id: 5, state: 'done' });
    await advanceTime(500);
    await contains('.mk_ai_systray_btn').click();
    expect(queryAllTexts('.mk_systray_chats .mk_systray_name')).toEqual([
        'From a cron',
    ]);
    seen.emit('muk_ai.session_state', { session_id: 5, deleted: true });
    await animationFrame();
    expect('.mk_systray_menu').toHaveText(/No chats yet\./);
});
