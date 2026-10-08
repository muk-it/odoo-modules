import {
    animationFrame,
    expect,
    queryAllTexts,
    resize,
    runAllTimers,
    test,
} from '@odoo/hoot';
import {
    contains,
    getService,
    makeServerError,
    mountWebClient,
    onRpc,
} from '@web/../tests/web_test_helpers';
import { router } from '@web/core/browser/router';
import { redirect } from '@web/core/utils/urls';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import {
    AISessionModel,
    defineAIModels,
    emit,
    emitEvent,
    LeadModel,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels(LeadModel);

const history = [{ kind: 'user_message', content: 'Hello', event_id: 1, sequence: 1 }];

async function openChatPage(params = {}) {
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.client',
        tag: 'muk_ai.chat',
        params,
    });
    await animationFrame();
}

function seedChats() {
    AISessionModel._records = [
        {
            id: 1,
            name: 'Older chat',
            state: 'done',
            create_date: '2026-01-01 10:00:00',
        },
        {
            id: 2,
            name: 'Latest chat',
            state: 'done',
            create_date: '2026-01-02 10:00:00',
        },
    ];
}

test('the page opens the requested chat with the sidebar folded, or else the latest chat', async () => {
    seedChats();
    await openChatPage({ session_id: 1 });
    expect('.mk_main_title').toHaveText('Older chat');
    expect('.mk_sidebar').toHaveCount(0);
    await runAllTimers();
    expect(router.current.resId).toBe(1);
    await contains('button[title="Toggle sidebar"]').click();
    expect('.mk_sidebar_item.active').toHaveText('Older chat');
    await contains('.mk_sidebar_item:contains(Latest chat)').click();
    expect('.mk_main_title').toHaveText('Latest chat');
    await runAllTimers();
    expect(router.current.resId).toBe(2);
});

for (const [url, sidebar] of [
    ['/odoo/ai-chat?session_id=1', 0],
    ['/odoo/ai-chat/1', 1],
]) {
    test.tags('desktop');
    test(`a fresh load of ${url} opens that chat, the sidebar open only on the own url of the page`, async () => {
        seedChats();
        redirect(url);
        await mountWebClient();
        await animationFrame();
        expect('.mk_main_title').toHaveText('Older chat');
        expect('.mk_sidebar').toHaveCount(sidebar);
    });
}

test.tags('desktop');
test('a record the chat opens docks the chat and keeps the page in the breadcrumb by name', async () => {
    seedChats();
    await openChatPage({ session_id: 1 });
    await emitEvent(1, 'ui_action', {
        action: {
            type: 'ir.actions.act_window',
            res_model: 'muk_ai.test_lead',
            res_id: 1,
            views: [[false, 'form']],
        },
    });
    await animationFrame();
    expect(getService(AIChatPlugin).windowIds).toEqual([1]);
    expect(
        queryAllTexts('.o_breadcrumb .breadcrumb-item, .o_breadcrumb .active'),
    ).toEqual(['MuK AI Chat', 'Acme']);
});

test.tags('desktop');
test('without a requested chat the page shows the latest one of the user', async () => {
    seedChats();
    await openChatPage();
    expect('.mk_main_title').toHaveText('Latest chat');
    expect('.mk_sidebar_item.active').toHaveText('Latest chat');
});

test.tags('desktop');
test('a user without chats is welcomed with suggestions, picking one starts a chat with it', async () => {
    AISessionModel._records = [];
    onRpc('muk_ai.session', 'start', ({ args }) => expect.step(`start ${args[1]}`));
    await openChatPage();
    expect('.mk_empty h2').toHaveText('How can I help you today?');
    await contains('.mk_empty .mk_suggestion').click();
    await animationFrame();
    expect.verifySteps(['start Show my **pipeline**']);
    expect('.mk_bubble_user').toHaveText('Show my **pipeline**');
    expect('.mk_sidebar_item.active').toHaveCount(1);
});

test('a chat that no longer exists is announced and replaced by the latest one', async () => {
    seedChats();
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) => {
        if (args[0] === 99) {
            throw makeServerError({ message: 'Record does not exist' });
        }
    });
    await openChatPage({ session_id: 99 });
    await animationFrame();
    expect('.o_notification').toHaveText('That AI session no longer exists.');
    expect('.mk_main_title').toHaveText('Latest chat');
});

test.tags('desktop');
test('a new chat starts on the page, not on the record the chat shown is pinned to', async () => {
    seedChats();
    const context = {
        kind: 'record',
        model: 'muk_ai.test_lead',
        id: 1,
        display_name: 'Acme',
    };
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        args[0] === 2
            ? { ...snapshot({ id: 2, name: 'Latest chat' }), view_context: context }
            : undefined,
    );
    onRpc('muk_ai.session', 'set_view_context', ({ args }) =>
        expect.step(`pin ${args[0]} ${args[1].model}`),
    );
    await openChatPage();
    expect('.mk_ctx_chip').toHaveCount(1);
    await contains('.mk_sidebar_header .btn-primary').click();
    expect('.mk_sidebar_item.active').toHaveAttribute('data-session-id', '3');
    expect('.mk_ctx_chip').toHaveCount(0);
    expect.verifySteps([]);
});

test('what is typed while a new chat is created goes to the new chat', async () => {
    seedChats();
    const created = Promise.withResolvers();
    onRpc('muk_ai.session', 'create', async () => {
        await created.promise;
    });
    await openChatPage();
    await contains('.mk_sidebar_header .btn-primary').click();
    await contains('.mk_composer textarea').edit('ABCDEF');
    created.resolve();
    await animationFrame();
    expect('.mk_sidebar_item.active').toHaveAttribute('data-session-id', '3');
    expect('.mk_composer textarea').toHaveValue('ABCDEF');
    await contains('.mk_sidebar_item:contains(Latest chat)').click();
    expect('.mk_composer textarea').toHaveValue('');
});

test.tags('desktop');
test('the header switches the agent and opens the search, the artifacts and a window', async () => {
    seedChats();
    onRpc('muk_ai.session', 'write', ({ args }) =>
        expect.step(`write ${JSON.stringify(args[1])}`),
    );
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshot({
            id: args[0],
            name: 'Latest chat',
            events: history,
            agent_id: [1, 'General'],
        }),
    );
    await openChatPage();
    await contains('.mk_agent_pill').click();
    expect(queryAllTexts('.o-dropdown--menu .dropdown-item', { inline: true })).toEqual(
        ['General Default agent', 'Analyst Analyses', 'No agent (defaults)'],
    );
    await contains('.o-dropdown--menu .dropdown-item:contains(Analyst)').click();
    expect.verifySteps(['write {"agent_id":2}']);
    expect('.mk_agent_pill').toHaveText('Analyst');
    await contains('button[title="Search this chat"]').click();
    expect('.mk_search_bar input').toBeFocused();
    await contains('button[title="Toggle artifacts panel"]').click();
    expect('.mk_artifacts_panel').toHaveCount(1);
    await contains('.mk_artifacts_panel button[title="Close artifacts panel"]').click();
    expect('.mk_artifacts_panel').toHaveCount(0);
    await contains('button[title="Pop out chat to a floating window"]').click();
    expect(getService(AIChatPlugin).windowIds).toEqual([2]);
});

test('a chat shared with the user keeps its agent and cannot be handed over', async () => {
    seedChats();
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshot({
            id: args[0],
            can_write: false,
            user_id: [9, 'Marc Demo'],
            agent_id: [1, 'General'],
        }),
    );
    await openChatPage({ session_id: 2 });
    expect('.mk_agent_pill').toHaveAttribute(
        'title',
        'The agent of a shared chat cannot be changed',
    );
    await contains('.mk_agent_pill').click();
    expect('.o-dropdown--menu').toHaveCount(0);
    expect('button[title="Hand over this chat to another user"]').toHaveCount(0);
});

test('when the chat shown is deleted elsewhere the page moves to the latest one', async () => {
    seedChats();
    await openChatPage({ session_id: 1 });
    await emit('muk_ai.session_state', { session_id: 1, deleted: true });
    await animationFrame();
    expect('.mk_main_title').toHaveText('Latest chat');
});

test('on a phone the page opens on the chat and the sidebar folds away once a chat is picked', async () => {
    resize({ width: 375, height: 667 });
    seedChats();
    await openChatPage();
    expect('.mk_sidebar').toHaveCount(0);
    expect('.mk_composer textarea').toHaveAttribute(
        'placeholder',
        'Message the assistant...',
    );
    await contains('button[title="Toggle sidebar"]').click();
    await contains('.mk_sidebar_item:contains(Older chat)').click();
    expect('.mk_sidebar').toHaveCount(0);
    expect('.mk_main_title').toHaveText('Older chat');
});
