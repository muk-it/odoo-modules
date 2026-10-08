import {
    advanceTime,
    animationFrame,
    dblclick,
    expect,
    mockDate,
    press,
    queryAllProperties,
    queryAllTexts,
    queryOne,
    test,
} from '@odoo/hoot';
import {
    contains,
    mountWithCleanup,
    MockServer,
    onRpc,
    serverState,
} from '@web/../tests/web_test_helpers';
import { browser } from '@web/core/browser/browser';

import { ChatSidebar } from '@muk_ai/chat/sidebar/sidebar';
import {
    AISessionModel,
    AISpaceModel,
    defineAIModels,
    emit,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const chat = (id, name, values = {}) => ({
    id,
    name,
    state: 'done',
    create_date: '2026-01-10 08:00:00',
    ...values,
});
const row = (id) => `.mk_sidebar_item[data-session-id="${id}"]`;

function trackWrites() {
    onRpc(({ model, method, args }) => {
        if (
            ['write', 'unlink', 'create'].includes(method) &&
            model.startsWith('muk_ai.')
        ) {
            expect.step(
                `${model} ${method} ${JSON.stringify(method === 'create' ? args[0] : args)}`,
            );
        }
    });
}

async function mountSidebar(props = {}) {
    mockDate('2026-01-10 12:00:00', 0);
    await mountWithCleanup(ChatSidebar, {
        props: {
            onSelect: (id) => expect.step(`select ${id}`),
            onNew: (values) => expect.step(`new ${JSON.stringify(values ?? {})}`),
            ...props,
        },
    });
}

test('the chats of the user group by day, show their state and select on click', async () => {
    AISessionModel._records = [
        chat(1, 'Morning', { state: 'running' }),
        chat(2, 'Last night', { state: 'waiting', create_date: '2026-01-09 20:00:00' }),
        chat(3, 'Monday', { state: 'error', create_date: '2026-01-05 09:00:00' }),
        chat(4, 'Autumn', { create_date: '2025-10-01 09:00:00' }),
        chat(5, 'Of a colleague', { user_id: serverState.publicUserId }),
    ];
    await mountSidebar({ activeId: 1 });
    expect(
        queryAllProperties('.mk_loose_group .mk_sidebar_heading', 'textContent'),
    ).toEqual(['Today', 'Yesterday', 'Previous 7 days', 'Older']);
    expect(queryAllTexts('.mk_loose_group .mk_sidebar_name')).toEqual([
        'Morning',
        'Last night',
        'Monday',
        'Autumn',
    ]);
    expect(`${row(1)}.active.mk_running .mk_sidebar_sub`).toHaveText('thinking...');
    expect(`${row(2)} .mk_sidebar_sub`).toHaveText('awaiting you');
    expect(`${row(3)} .mk_state_error`).toHaveCount(1);
    await contains(row(3)).click();
    await contains('.mk_sidebar_header .btn-primary').click();
    expect.verifySteps(['select 3', 'new {}']);
});

test('a search lists the matching chats of every space after a pause, clearing it brings the spaces back', async () => {
    AISpaceModel._records = [{ id: 5, name: 'Sales', icon: 'sell' }];
    AISessionModel._records = [
        chat(1, 'Sales report', { space_id: 5 }),
        chat(2, 'Weekly report', { create_date: '2026-01-10 09:00:00' }),
        chat(3, 'Lunch'),
    ];
    await mountSidebar();
    expect(queryAllTexts('.mk_loose_group .mk_sidebar_name')).toEqual([
        'Weekly report',
        'Lunch',
    ]);
    await contains('.mk_sidebar_search input').edit('report', { confirm: false });
    await advanceTime(250);
    await animationFrame();
    expect(queryAllTexts('.mk_sidebar_name')).toEqual([
        'Weekly report',
        'Sales report',
    ]);
    expect(`${row(1)} .mk_space_chip`).toHaveText('Sales');
    expect('.mk_space_row').toHaveCount(0);
    await contains('.mk_sidebar_search input').edit('zzz', { confirm: false });
    await advanceTime(250);
    await animationFrame();
    expect('.mk_sidebar_list').toHaveText('No chats match zzz.');
    await contains('.mk_sidebar_search button[title=Clear]').click();
    expect(queryAllTexts('.mk_space_name')).toEqual(['Sales']);
    expect(queryAllTexts('.mk_loose_group .mk_sidebar_name')).toEqual([
        'Weekly report',
        'Lunch',
    ]);
});

test('a space unfolds into its chats page by page, its unread badge narrows them to the unread', async () => {
    AISpaceModel._records = [{ id: 5, name: 'Sales', icon: 'sell' }];
    AISessionModel._records = Array.from({ length: 11 }, (_, index) =>
        chat(index + 1, `Deal ${index + 1}`, {
            space_id: 5,
            create_date: `2026-01-${20 - index} 10:00:00`,
            notification_unread: index === 4,
        }),
    );
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 1,
        session_ids: [5],
        space_unread: { 5: 1 },
    }));
    await mountSidebar();
    expect('.mk_space_row .mk_space_icon').toHaveAttribute('data-icon', 'sell');
    await contains('.mk_space_row').click();
    expect('.mk_space_branch .mk_sidebar_item').toHaveCount(10);
    await contains('.mk_space_branch .mk_load_more').click();
    expect('.mk_space_branch .mk_sidebar_item').toHaveCount(11);
    await contains('.mk_space_badge').click();
    expect('.mk_space_filter').toHaveText('Unread only');
    expect(queryAllTexts('.mk_space_branch .mk_sidebar_name')).toEqual(['Deal 5']);
    expect(`${row(5)}.mk_unread .mk_sidebar_unread`).toHaveCount(1);
    await contains('.mk_space_filter button').click();
    expect('.mk_space_branch .mk_sidebar_item').toHaveCount(10);
    await contains('.mk_space_row').click();
    expect('.mk_space_branch').toHaveCount(0);
});

test('system spaces are pinned or folded under Automatic, which counts their unread chats', async () => {
    AISpaceModel._records = [
        { id: 6, name: 'Inbox', system: true, pinned: true },
        { id: 7, name: 'Scheduled', system: true },
        { id: 8, name: 'Mail', system: true },
    ];
    onRpc('muk_ai.session', 'notification_badge', () => ({
        count: 3,
        session_ids: [],
        space_unread: { 7: 2, 8: 1 },
    }));
    await mountSidebar();
    expect('.mk_sidebar_list').toHaveText(/No space yet\. Create a new space\./);
    expect(queryAllTexts('.mk_space_name')).toEqual(['Inbox']);
    expect(queryAllTexts('.mk_space_auto .mk_space_count')).toEqual(['3', '2']);
    await contains('.mk_space_auto').click();
    expect(queryAllTexts('.mk_space_name')).toEqual(['Inbox', 'Scheduled', 'Mail']);
    expect(queryAllTexts('.mk_space_system .mk_space_badge')).toEqual(['2', '1']);
    expect(
        '.mk_space_system .mk_space_grip, .mk_space_system .mk_space_actions',
    ).toHaveCount(0);
    expect(browser.localStorage.getItem('muk_ai.sidebar_automatic_open')).toBe('1');
});

test('a space is created from its inline field on Enter, Escape drops the name', async () => {
    trackWrites();
    await mountSidebar();
    await contains('button[title="New space"]').click();
    expect('.mk_space_new input').toBeFocused();
    await contains('.mk_space_new input').edit('Draft', { confirm: false });
    await press('Escape');
    await animationFrame();
    expect('.mk_space_new').toHaveCount(0);
    await contains('button[title="New space"]').click();
    await contains('.mk_space_new input').edit('Projects', { confirm: false });
    await press('Enter');
    await animationFrame();
    expect.verifySteps(['muk_ai.space create [{"name":"Projects"}]']);
    expect(queryAllTexts('.mk_space_name')).toEqual(['Projects']);
});

test('a chat is renamed in a dialog saving on Enter once changed, and deleted after a confirmation', async () => {
    trackWrites();
    AISessionModel._records = [chat(1, 'Morning'), chat(2, 'Evening')];
    await mountSidebar();
    await contains(`${row(1)} button[title=Rename]`, { visible: false }).click();
    expect('.modal input').toHaveValue('Morning');
    expect('.modal .btn-primary').toHaveProperty('disabled', true);
    await contains('.modal input').edit('Plans', { confirm: false });
    await press('Enter');
    await animationFrame();
    expect('.modal').toHaveCount(0);
    expect(`${row(1)} .mk_sidebar_name`).toHaveText('Plans');
    await contains(`${row(1)} .mk_delete`, { visible: false }).click();
    expect('.modal-body').toHaveText('Delete "Plans"? This cannot be undone.');
    await contains('.modal .btn-danger').click();
    expect(queryAllTexts('.mk_sidebar_name')).toEqual(['Evening']);
    expect.verifySteps([
        'muk_ai.session write [[1],{"name":"Plans"}]',
        'muk_ai.session unlink [[1]]',
    ]);
});

test('a space is edited in a dialog saving its icon and instructions, and deleted keeping its chats', async () => {
    trackWrites();
    AISpaceModel._records = [{ id: 5, name: 'Sales', icon: 'sell' }];
    AISessionModel._records = [chat(1, 'Deal', { space_id: 5 })];
    onRpc('muk_ai.space', 'fetch_general_domain', () => [['space_id', '=', false]]);
    await mountSidebar();
    await contains('.mk_space_actions button[title=Edit]', { visible: false }).click();
    expect('.modal .btn-primary').toHaveProperty('disabled', true);
    await contains('.modal .mk_icon_picker .o_select_menu_toggler').click();
    await contains('.o_select_menu_item:has([data-icon=star])').click();
    await contains('.modal textarea').edit('Be brief', { confirm: false });
    await contains('.modal .btn-primary').click();
    expect.verifySteps([
        'muk_ai.space write [[5],{"name":"Sales","icon":"star","agent_id":false,"instructions":"Be brief"}]',
    ]);
    expect('.mk_space_icon').toHaveAttribute('data-icon', 'star');
    await contains('.mk_space_actions .mk_delete', { visible: false }).click();
    await contains('.modal .btn-danger').click();
    expect.verifySteps(['muk_ai.space unlink [[5]]']);
    expect('.mk_space_row').toHaveCount(0);
});

test('the list follows the bus: a new chat slots in by date, a renamed one updates, a deleted one goes', async () => {
    AISessionModel._records = [
        chat(1, 'Morning'),
        chat(2, 'Dawn', { create_date: '2026-01-10 06:00:00' }),
    ];
    await mountSidebar();
    const [id] = MockServer.env['muk_ai.session'].create([
        { name: 'Fresh', create_date: '2026-01-10 07:00:00' },
    ]);
    await emit('muk_ai.session_state', { session_id: id, state: 'running' });
    await animationFrame();
    expect(queryAllTexts('.mk_sidebar_name')).toEqual(['Morning', 'Fresh', 'Dawn']);
    await emit('muk_ai.session_state', {
        session_id: 1,
        name: 'Briefing',
        state: 'running',
    });
    expect(`${row(1)} .mk_sidebar_name`).toHaveText('Briefing');
    expect(`${row(1)}.mk_running`).toHaveCount(1);
    await emit('muk_ai.session_state', { session_id: 1, deleted: true });
    expect(queryAllTexts('.mk_sidebar_name')).toEqual(['Fresh', 'Dawn']);
});

test('a chat dragged onto a space is filed into it', async () => {
    trackWrites();
    AISpaceModel._records = [{ id: 5, name: 'Sales' }];
    AISessionModel._records = [chat(1, 'Deal'), chat(2, 'Lunch')];
    await mountSidebar();
    await contains(row(1)).dragAndDrop(
        '.mk_space_personal[data-space-id="5"] .mk_space_row',
    );
    await animationFrame();
    expect.verifySteps(['muk_ai.session write [[1],{"space_id":5}]']);
    expect(queryAllTexts('.mk_loose_group .mk_sidebar_name')).toEqual(['Lunch']);
    expect(queryAllTexts('.mk_space_branch .mk_sidebar_name')).toEqual(['Deal']);
});

test.tags('desktop');
test('loose chats load page by page and the panel keeps the width it was given', async () => {
    browser.localStorage.setItem('muk_ai.sidebar_width', '400');
    AISessionModel._records = Array.from({ length: 21 }, (_, index) =>
        chat(index + 1, `Chat ${index + 1}`),
    );
    await mountSidebar();
    expect('.mk_sidebar').toHaveStyle({ width: '400px' });
    expect('.mk_loose_group .mk_sidebar_item').toHaveCount(20);
    await contains('.mk_sidebar_list > .mk_load_more').click();
    expect('.mk_loose_group .mk_sidebar_item').toHaveCount(21);
    expect('.mk_sidebar_list > .mk_load_more').toHaveCount(0);
    await dblclick(queryOne('.mk_sidebar > .o_resizable_panel_handle'));
    expect('.mk_sidebar').toHaveStyle({ width: '272px' });
    expect(browser.localStorage.getItem('muk_ai.sidebar_width')).toBe('272');
});
