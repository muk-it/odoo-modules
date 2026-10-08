import {
    advanceTime,
    after,
    animationFrame,
    expect,
    manuallyDispatchProgrammaticEvent,
    queryAllTexts,
    queryOne,
    scroll,
    test,
} from '@odoo/hoot';
import { Component, t, useProps, xml } from '@odoo/owl';
import { contains, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import {
    ChatConversation,
    composerAccessories,
    transcriptFooters,
} from '@muk_ai/chat/conversation/conversation';
import {
    defineAIModels,
    emitEvent,
    openSession,
    pngFile,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const history = [
    { kind: 'user_message', content: 'Question', event_id: 1, sequence: 1 },
    { kind: 'text', content: 'Answer', event_id: 2, sequence: 2 },
];

async function mountConversation(values = {}, props = {}) {
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({ events: history, iteration_count: 1, ...values }),
    );
    const session = await openSession(1);
    await mountWithCleanup(ChatConversation, { props: { session, ...props } });
    return session;
}

test('a running chat draws its stream, its tools and its queue', async () => {
    onRpc('muk_ai.session', 'cancel_queued', ({ args }) => {
        expect.step(`cancel ${args[1]}`);
        return snapshot({ state: 'running', events: history });
    });
    await mountConversation({
        state: 'running',
        pending_user_messages: [{ content: 'Next one' }],
    });
    expect('.mk_streaming .mk_thinking').toHaveText('Thinking');
    await emitEvent(1, 'reasoning_delta', { delta: 'Checking the ledger' });
    expect('.mk_streaming .mk_thinking').toHaveText('Checking the ledger');
    await emitEvent(1, 'tool_call_start', { call_id: 'c1', name: 'read_group' });
    expect('.mk_tool.mk_tool_streaming .mk_tool_name').toHaveText('read_group');
    await emitEvent(1, 'text_delta', { delta: '**Half**' });
    expect('.mk_streaming strong').toHaveText('Half');
    expect('.mk_streaming .mk_thinking').toHaveCount(0);
    await advanceTime(3000);
    expect('.mk_streaming .mk_thinking').toHaveText('Checking the ledger');
    expect('.mk_bubble_queued').toHaveText('Next one');
    await contains('.mk_queue_cancel').click();
    expect.verifySteps(['cancel 0']);
});

test('an error is shown with the way to regenerate the answer', async () => {
    onRpc('muk_ai.session', 'regenerate_last_turn', () => {
        expect.step('regenerate');
        return snapshot({ state: 'running', events: history });
    });
    await mountConversation({ state: 'error', error_message: 'Quota exceeded' });
    expect('.alert-danger').toHaveText(/Quota exceeded/);
    await contains('.alert-danger button').click();
    expect.verifySteps(['regenerate']);
    expect('.alert-danger').toHaveCount(0);
});

test('an empty chat offers the suggestions of its agent, previewed without markdown', async () => {
    onRpc('muk_ai.session', 'start', ({ args }) => {
        expect.step(args[1]);
        return snapshot({ state: 'running' });
    });
    await mountConversation({
        events: [],
        iteration_count: 0,
        agent_id: [1, 'General'],
    });
    expect('.mk_suggestion_label').toHaveText(/^pipeline$/i);
    expect('.mk_suggestion_preview').toHaveText('Show my pipeline');
    await contains('.mk_suggestion').click();
    expect.verifySteps(['Show my **pipeline**']);
    expect('.mk_bubble_user').toHaveText('Show my **pipeline**');
});

test('files pasted in the chat or on the bare page are attached, elsewhere they are not', async () => {
    let nextId = 10;
    onRpc('muk_ai.session', 'upload_attachments', ({ args }) => {
        expect.step(args[1].map((file) => file.filename).join());
        return args[1].map((file) => ({
            id: nextId++,
            filename: file.filename,
            mimetype: 'image/png',
        }));
    });
    await mountConversation();
    const outside = document.createElement('input');
    document.body.append(outside);
    for (const [target, name] of [
        [queryOne('.mk_composer textarea'), 'composer.png'],
        [queryOne('.mk_messages'), 'transcript.png'],
        [document.body, 'page.png'],
        [outside, 'form.png'],
    ]) {
        const clipboardData = new DataTransfer();
        clipboardData.items.add(pngFile(name));
        await manuallyDispatchProgrammaticEvent(target, 'paste', { clipboardData });
        await animationFrame();
    }
    outside.remove();
    expect.verifySteps(['composer.png', 'transcript.png', 'page.png']);
    expect('.mk_composer .mk_att_card').toHaveCount(3);
});

test('older messages load from the button above the transcript', async () => {
    onRpc('muk_ai.session', 'fetch_events', () => ({
        events: [{ kind: 'user_message', content: 'Oldest', event_id: 0, sequence: 0 }],
        oldest_sequence: 0,
        has_more_older: false,
    }));
    await mountConversation({ has_more_older: true, oldest_sequence: 1 });
    await contains('.mk_load_older button').click();
    expect(queryAllTexts('.mk_bubble_user .mk_bubble_text')).toEqual([
        'Oldest',
        'Question',
    ]);
    expect('.mk_load_older').toHaveCount(0);
});

test('addons hang cards under the transcript and above the composer of every chat', async () => {
    class Plan extends Component {
        static template = xml`<div class="o_test_plan">Plan of chat <t t-out="this.props.session.id"/></div>`;
        props = useProps({ session: t.object() });
    }
    class Todo extends Component {
        static template = xml`<div class="o_test_todo">Todo</div>`;
    }
    transcriptFooters.add(Plan);
    composerAccessories.add(Todo);
    after(() => {
        transcriptFooters.delete(Plan);
        composerAccessories.delete(Todo);
    });
    await mountConversation();
    expect('.mk_messages_inner .o_test_plan').toHaveText('Plan of chat 1');
    expect('.mk_composer_wrap .o_test_todo + .mk_composer_host').toHaveCount(1);
});

test('a compact conversation has no share bar, hint nor pills under its composer', async () => {
    await mountConversation({}, { compact: true });
    expect('.mk_conversation_compact').toHaveCount(1);
    expect('.mk_share_bar, .mk_composer_meta').toHaveCount(0);
});

test('the transcript follows new messages until scrolled up, offers the way back and loads older ones at its top', async () => {
    class Frame extends Component {
        static template = xml`<div class="d-flex flex-column" style="height: 300px"><ChatConversation session="this.props.session" compact="true"/></div>`;
        static components = { ChatConversation };
        props = useProps({ session: t.object() });
    }
    const message = (index) => ({
        kind: 'user_message',
        content: `Message ${index}`,
        event_id: index,
        sequence: index,
    });
    onRpc('muk_ai.session', 'get_snapshot', () =>
        snapshot({
            events: Array.from({ length: 30 }, (_, index) => message(index + 1)),
            iteration_count: 1,
            has_more_older: true,
            oldest_sequence: 1,
        }),
    );
    onRpc('muk_ai.session', 'fetch_events', () => ({
        events: [message(0)],
        oldest_sequence: 0,
        has_more_older: false,
    }));
    const session = await openSession(1);
    await mountWithCleanup(Frame, { props: { session } });
    await animationFrame();
    const scroller = queryOne('.mk_messages');
    const fromBottom = () =>
        scroller.scrollHeight - scroller.clientHeight - scroller.scrollTop;
    expect(fromBottom()).toBeLessThan(2);
    await emitEvent(1, 'log', message(31));
    await animationFrame();
    expect(fromBottom()).toBeLessThan(2);
    await scroll(scroller, { top: 400 });
    await emitEvent(1, 'log', message(32));
    await animationFrame();
    expect(scroller.scrollTop).toBe(400);
    await contains('.mk_scroll_bottom').click();
    await animationFrame();
    expect(fromBottom()).toBeLessThan(2);
    expect('.mk_scroll_bottom').toHaveCount(0);
    await scroll(scroller, { top: 0 });
    await animationFrame();
    await animationFrame();
    expect('.mk_bubble_text:first').toHaveText('Message 0');
    expect(scroller.scrollTop).toBeGreaterThan(0);
});
