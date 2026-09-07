import { describe, expect, test } from '@odoo/hoot';
import {
    animationFrame,
    click,
    press,
    queryAll,
    queryAllTexts,
    queryFirst,
} from '@odoo/hoot-dom';
import { Component, useState, xml } from '@odoo/owl';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { sessionChannel } from '@muk_ai/chat/session/session_channel';

import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel';

describe.current.tags('muk_ai_chatter');
defineMailModels();

const SESSION_ID = 42;

const DRAFT = 'Dear customer, thanks for you order.';

const SELECTION = 'thanks for you order';

const SKILLS = [
    {
        name: 'compose_shorten',
        label: 'Shorten',
        icon: 'fa-compress',
        category: 'rewrite',
        description: 'Say the same thing in fewer words.',
        body: 'Shorten it.',
    },
    {
        name: 'compose_fix_grammar',
        label: 'Fix grammar',
        icon: 'fa-check',
        category: 'fix',
        description: 'Correct spelling and grammar.',
        body: 'Fix it.',
    },
    {
        name: 'compose_reply',
        label: 'Reply',
        icon: 'fa-reply',
        category: 'generate',
        description: 'Answer the last message.',
        body: 'Reply to it.',
    },
];

/**
 * Install a bus mock that pushes an event to every subscriber, as the real one
 * does: the panel is not the only thing listening for session events, and the
 * channel a notification arrived on is not the one deciding who is told.
 * @returns {{notify: (event: object) => void, channels: string[]}} the mock
 */
function mockBus() {
    const handlers = [];
    const channels = [];
    mockService('bus_service', {
        subscribe(type, handler) {
            if (type === 'muk_ai.event') {
                handlers.push(handler);
            }
        },
        unsubscribe() {},
        addChannel(channel) {
            channels.push(channel);
        },
        deleteChannel(channel) {
            const index = channels.indexOf(channel);
            if (index !== -1) {
                channels.splice(index, 1);
            }
        },
    });
    return {
        notify: (event) => handlers.forEach((handler) => handler(event)),
        channels,
    };
}

/**
 * Stub the server the panel talks to and record what it was asked.
 * @returns {{sent: string[], opened: object[], detached: boolean}} the calls made
 */
function mockServer() {
    const calls = {
        sent: [],
        opened: [],
        context: [],
        detached: false,
        discarded: false,
        openFails: false,
        saved: [],
        state: 'done',
        answer: 'A better sentence.',
    };
    onRpc('muk_ai.skill', 'fetch_skills', () => SKILLS);
    onRpc('muk_ai.session', 'open_for_composer', ({ kwargs }) => {
        if (calls.openFails) {
            throw new Error('no agent available');
        }
        calls.opened.push(kwargs);
        return { id: SESSION_ID, state: 'new' };
    });
    onRpc('muk_ai.session', 'discard_unused_composer', () => {
        calls.discarded = true;
        return true;
    });
    onRpc('muk_ai.session', 'update_compose_context', ({ args }) => {
        calls.context.push({ draft: args[1], selection: args[2] });
        return true;
    });
    onRpc('muk_ai.session', 'send_message', ({ args }) => {
        calls.sent.push(args[1]);
        return {};
    });
    onRpc('muk_ai.session', 'detach_from_composer', () => {
        calls.detached = true;
        return true;
    });
    onRpc('muk_ai.skill', 'save_composer_prompt', ({ args }) => {
        calls.saved.push(args);
        return {
            name: 'saved_button',
            label: args[0],
            icon: 'fa-magic',
            category: args[2],
            description: args[1],
            body: args[1],
        };
    });
    onRpc('muk_ai.session', 'read', () => [
        { id: SESSION_ID, last_text: calls.answer, state: calls.state },
    ]);
    return calls;
}

/**
 * Build an adapter standing in for a composer, recording what is applied.
 * @param {string} [selection] the text the user had selected
 * @param {string} [draft] everything already written in the composer
 * @returns {object} the adapter, with an `applied` log
 */
function makeAdapter(selection = '', draft = '') {
    return {
        interfaceKey: 'mail_composer',
        applied: [],
        getDraft: () => draft,
        getSelection: () => selection,
        applySelection(text) {
            this.applied.push(['selection', text]);
        },
        applyDraft(text) {
            this.applied.push(['draft', text]);
        },
        replaceDraft(text) {
            this.applied.push(['replaced', text]);
        },
        getRecord: () => ({ resModel: 'res.partner', resId: 7 }),
    };
}

/**
 * Hold a panel that can be taken away again, as closing a composer does.
 */
class PanelHolder extends Component {
    static components = { ComposePanel };
    static props = { adapter: Object };
    static template = xml`<ComposePanel t-if="state.shown" adapter="props.adapter"/>`;

    setup() {
        this.state = useState({ shown: true });
    }
}

/**
 * Mount the panel over an adapter and return what it was mounted with.
 * @param {string} [selection] the text the user had selected
 * @param {string} [draft] everything already written in the composer
 * @returns {Promise<{panel: ComposePanel, adapter: object, closed: number[]}>} the fixture
 */
async function mountPanel(selection = '', draft = '') {
    const adapter = makeAdapter(selection, draft);
    const closed = [];
    const panel = await mountWithCleanup(ComposePanel, {
        props: { adapter, close: () => closed.push(1) },
    });
    return { panel, adapter, closed };
}

/**
 * Pick the first offer the panel makes, opening its group when it has one.
 * @returns {Promise<void>} once the run has been asked for
 */
async function pickFirst() {
    await click('.o-mail-ComposePanel-action');
    await animationFrame();
    if (queryFirst('.o-mail-ComposePanel-chip')) {
        await click('.o-mail-ComposePanel-chip');
        await animationFrame();
    }
}

/**
 * Type into a field the way the panel's own inputs expect.
 * @param {string} selector the field to fill
 * @param {string} value what to type
 * @returns {Promise<void>} once the panel has re-rendered
 */
async function typeInto(selector, value) {
    const input = queryFirst(selector);
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await animationFrame();
}

test('an empty composer offers one action, and reveals the rest on demand', async () => {
    mockBus();
    mockServer();
    await mountPanel();
    expect(queryAllTexts('.o-mail-ComposePanel-action')).toEqual(['Reply']);
    expect('.o-mail-ComposePanel-length').toHaveCount(0);
    expect('.o-mail-ComposePanel-tone').toHaveCount(0);
    await click('.o-mail-ComposePanel-action');
    await animationFrame();
    expect(queryAllTexts('.o-mail-ComposePanel-chip')).toEqual([
        'Reply',
        'New quick action',
    ]);
    expect('.o-mail-ComposePanel-length').toHaveCount(3);
    expect('.o-mail-ComposePanel-tone').toHaveCount(3);
});

test('a selection is offered the transforms, and no length or tone', async () => {
    mockBus();
    mockServer();
    await mountPanel(SELECTION, DRAFT);
    expect(queryAllTexts('.o-mail-ComposePanel-action')).toEqual([
        'Fix grammar',
        'Shorten',
    ]);
    expect('.o-mail-ComposePanel-length').toHaveCount(0);
    expect('.o-mail-ComposePanel-tone').toHaveCount(0);
});

test('a draft nobody selected is itself what gets rewritten', async () => {
    mockBus();
    mockServer();
    await mountPanel('', DRAFT);
    expect(queryAllTexts('.o-mail-ComposePanel-action')).toEqual([
        'Fix grammar',
        'Shorten',
    ]);
    expect('.o-mail-ComposePanel-length').toHaveCount(0);
    expect('.o-mail-ComposePanel-tone').toHaveCount(0);
    expect('.o-mail-ComposePanel-quote').toHaveText(DRAFT);
});

test('the session is opened with the draft and the selection', async () => {
    mockBus();
    const calls = mockServer();
    await mountPanel(SELECTION, DRAFT);
    expect(calls.opened).toHaveLength(1);
    expect(calls.opened[0].selection).toBe(SELECTION);
    expect(calls.opened[0].draft).toBe(DRAFT);
    expect(calls.opened[0].res_model).toBe('res.partner');
});

test('rewriting a whole draft sends it as the part to rewrite', async () => {
    mockBus();
    const calls = mockServer();
    await mountPanel('', DRAFT);
    expect(calls.opened[0].selection).toBe('');
    await pickFirst();
    expect(calls.context).toEqual([{ draft: DRAFT, selection: DRAFT }]);
});

test('the chosen length and tone are carried into the instruction', async () => {
    mockBus();
    const calls = mockServer();
    await mountPanel();
    await click('.o-mail-ComposePanel-action');
    await animationFrame();
    await click('.o-mail-ComposePanel-length:last-child');
    await click('.o-mail-ComposePanel-tone:last-child');
    await click('.o-mail-ComposePanel-chip');
    await animationFrame();
    expect(calls.sent[0]).toInclude('Reply to it.');
    expect(calls.sent[0]).toInclude('more room');
    expect(calls.sent[0]).toInclude('friendly');
});

test('a rewrite carries no length or tone of its own', async () => {
    mockBus();
    const calls = mockServer();
    await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    expect(calls.sent[0]).toBe('Fix it.');
});

test('the answer streams in while it is being written', async () => {
    const { notify } = mockBus();
    mockServer();
    await mountPanel();
    await pickFirst();
    expect('.o-mail-ComposePanel-busy').toHaveCount(1);
    notify({
        session_id: SESSION_ID,
        type: 'text_delta',
        payload: { delta: 'Half ' },
    });
    await animationFrame();
    expect('.o-mail-ComposePanel-stream').toHaveText('Half');
});

test('the panel listens on the channel of the session it holds', async () => {
    const { channels } = mockBus();
    mockServer();
    const holder = await mountWithCleanup(PanelHolder, {
        props: { adapter: makeAdapter() },
    });
    expect(channels).toEqual([sessionChannel(SESSION_ID)]);
    holder.state.shown = false;
    await animationFrame();
    expect(channels).toEqual([]);
});

test('a delta from another session is ignored', async () => {
    const { notify } = mockBus();
    mockServer();
    await mountPanel();
    await pickFirst();
    notify({
        session_id: SESSION_ID + 1,
        type: 'text_delta',
        payload: { delta: 'Nope' },
    });
    await animationFrame();
    expect('.o-mail-ComposePanel-stream').toHaveCount(0);
});

test('a finished rewrite is shown as a diff, and replaces the selection', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    calls.answer = 'thank you for your order';
    const { adapter, closed } = await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-diff').toHaveCount(1);
    expect(queryAll('.o-mail-ComposePanel-added').length).toBeGreaterThan(0);
    expect(queryAll('.o-mail-ComposePanel-removed').length).toBeGreaterThan(0);
    expect(queryAllTexts('.o-mail-ComposePanel-added').join(' ')).toInclude('your');
    expect('.o-mail-ComposePanel-accept').toHaveText('Replace selection');
    await click('.o-mail-ComposePanel-accept');
    await animationFrame();
    expect(adapter.applied).toEqual([['selection', 'thank you for your order']]);
    expect(closed).toHaveLength(1);
});

test('a rewritten draft replaces the whole message, not the cursor', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    calls.answer = 'Dear customer, thank you for your order.';
    const { adapter } = await mountPanel('', DRAFT);
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-diff').toHaveCount(1);
    expect('.o-mail-ComposePanel-accept').toHaveText('Replace message');
    await click('.o-mail-ComposePanel-accept');
    await animationFrame();
    expect(adapter.applied).toEqual([
        ['replaced', 'Dear customer, thank you for your order.'],
    ]);
});

test('a finished draft is shown plainly, and inserted at the cursor', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    calls.answer = 'A fresh message.';
    const { adapter } = await mountPanel();
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-diff').toHaveCount(0);
    expect('.o-mail-ComposePanel-result').toHaveText('A fresh message.');
    expect('.o-mail-ComposePanel-accept').toHaveText('Insert');
    await click('.o-mail-ComposePanel-accept');
    await animationFrame();
    expect(adapter.applied).toEqual([['draft', 'A fresh message.']]);
});

test('nothing reaches the composer until it is accepted', async () => {
    const { notify } = mockBus();
    mockServer();
    const { adapter } = await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect(adapter.applied).toHaveLength(0);
    await click('.o-mail-ComposePanel-discard');
    await animationFrame();
    expect(adapter.applied).toHaveLength(0);
    expect('.o-mail-ComposePanel-action').toHaveCount(2);
});

test('a failed run says so instead of offering nothing', async () => {
    const { notify } = mockBus();
    mockServer();
    await mountPanel();
    await pickFirst();
    notify({
        session_id: SESSION_ID,
        type: 'state',
        payload: { state: 'error', error: 'provider exploded' },
    });
    await animationFrame();
    expect('.o-mail-ComposePanel-error').toHaveText('provider exploded');
    expect('.o-mail-ComposePanel-action').toHaveCount(1);
});

test('an empty answer is reported rather than inserted', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    calls.answer = '';
    const { adapter } = await mountPanel();
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-error').toHaveCount(1);
    expect(adapter.applied).toHaveLength(0);
});

test('asking for something else sends what was typed', async () => {
    mockBus();
    const calls = mockServer();
    await mountPanel();
    const input = queryFirst('.o-mail-ComposePanel-custom');
    input.value = 'Make it rhyme';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await animationFrame();
    await click('.o-mail-ComposePanel-send');
    await animationFrame();
    expect(calls.sent[0]).toInclude('Make it rhyme');
});

test('a done published from the middle of a run is not taken as the answer', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    calls.state = 'running';
    await mountPanel();
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-busy').toHaveCount(1);
    expect('.o-mail-ComposePanel-accept').toHaveCount(0);
    calls.state = 'done';
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-accept').toHaveCount(1);
});

test('a run stopped from somewhere else still offers what it wrote', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    calls.state = 'stopped';
    calls.answer = 'Half a message.';
    await mountPanel();
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'stopped' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-result').toHaveText('Half a message.');
});

test('a helper nobody asked anything is dropped when the panel closes', async () => {
    mockBus();
    const calls = mockServer();
    const { panel } = await mountPanel();
    panel.discardUnusedSession();
    await animationFrame();
    expect(calls.discarded).toBe(true);
});

test('a helper that answered something is kept when the panel closes', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    const { panel } = await mountPanel();
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    panel.discardUnusedSession();
    await animationFrame();
    expect(calls.discarded).toBe(false);
});

test('the chips still work after the session failed to open', async () => {
    mockBus();
    const calls = mockServer();
    calls.openFails = true;
    await mountPanel();
    expect('.o-mail-ComposePanel-error').toHaveCount(1);
    calls.openFails = false;
    await pickFirst();
    expect(calls.sent).toHaveLength(1);
});

test('the chat window takes the session over, and the panel steps aside', async () => {
    mockBus();
    const calls = mockServer();
    const opened = [];
    mockService('muk_ai.chat_window', { open: (id) => opened.push(id) });
    const { closed } = await mountPanel();
    await click('.o-mail-ComposePanel-chat');
    await animationFrame();
    expect(calls.detached).toBe(true);
    expect(opened).toEqual([SESSION_ID]);
    expect(closed).toHaveLength(1);
});

test('a second helper closes the one that was already open', async () => {
    mockBus();
    mockServer();
    const first = await mountPanel();
    expect(first.closed).toHaveLength(0);
    await mountPanel();
    expect(first.closed).toHaveLength(1);
});

test('a free-text ask that worked offers to become a quick action', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    await mountPanel();
    await typeInto('.o-mail-ComposePanel-custom', 'Make it rhyme');
    await click('.o-mail-ComposePanel-send');
    await animationFrame();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect(calls.sent).toHaveLength(1);
    expect('.o-mail-ComposePanel-saveOpen').toHaveCount(1);
});

test('a chip that ran offers nothing to save, since it already is one', async () => {
    const { notify } = mockBus();
    mockServer();
    await mountPanel();
    await pickFirst();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    expect('.o-mail-ComposePanel-saveOpen').toHaveCount(0);
});

test('naming a free-text ask saves it as a button of its own', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    await mountPanel();
    await typeInto('.o-mail-ComposePanel-custom', 'Make it rhyme');
    await click('.o-mail-ComposePanel-send');
    await animationFrame();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    await click('.o-mail-ComposePanel-saveOpen');
    await animationFrame();
    await typeInto('.o-mail-ComposePanel-saveLabel', 'Rhyme it');
    await click('.o-mail-ComposePanel-saveConfirm');
    await animationFrame();
    expect(calls.saved).toEqual([['Rhyme it', 'Make it rhyme', 'generate']]);
    expect('.o-mail-ComposePanel-saved').toHaveCount(1);
});

test('the same ask over a draft is saved as a rewrite', async () => {
    const { notify } = mockBus();
    const calls = mockServer();
    await mountPanel('', 'Something already written.');
    await typeInto('.o-mail-ComposePanel-custom', 'Make it rhyme');
    await click('.o-mail-ComposePanel-send');
    await animationFrame();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    await click('.o-mail-ComposePanel-saveOpen');
    await animationFrame();
    await typeInto('.o-mail-ComposePanel-saveLabel', 'Rhyme it');
    await click('.o-mail-ComposePanel-saveConfirm');
    await animationFrame();
    expect(calls.saved[0][2]).toBe('rewrite');
});

test('a quick action can be written from scratch without running it', async () => {
    mockBus();
    const calls = mockServer();
    await mountPanel();
    await click('.o-mail-ComposePanel-chipNew');
    await animationFrame();
    expect('.o-mail-ComposePanel-createRow').toHaveCount(1);
    await typeInto('.o-mail-ComposePanel-createLabel', 'From scratch');
    await typeInto('.o-mail-ComposePanel-createBody', 'Do the thing.');
    await click('.o-mail-ComposePanel-createConfirm');
    await animationFrame();
    expect(calls.saved).toEqual([['From scratch', 'Do the thing.', 'generate']]);
    expect('.o-mail-ComposePanel-createRow').toHaveCount(0);
});

test('escape folds the naming row without closing the panel', async () => {
    const { notify } = mockBus();
    mockServer();
    const { closed } = await mountPanel();
    await typeInto('.o-mail-ComposePanel-custom', 'Make it rhyme');
    await click('.o-mail-ComposePanel-send');
    await animationFrame();
    notify({ session_id: SESSION_ID, type: 'state', payload: { state: 'done' } });
    await animationFrame();
    await animationFrame();
    await click('.o-mail-ComposePanel-saveOpen');
    await animationFrame();
    await press('Escape');
    await animationFrame();
    expect('.o-mail-ComposePanel-saveLabel').toHaveCount(0);
    expect(closed).toEqual([]);
});
