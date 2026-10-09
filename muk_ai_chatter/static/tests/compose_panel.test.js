import { animationFrame, describe, expect, test } from '@odoo/hoot';
import { click, press, queryAllTexts, queryFirst } from '@odoo/hoot-dom';
import { Component, proxy, xml } from '@odoo/owl';
import {
    contains,
    getService,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { defineAIModels, emitEvent } from '@muk_ai/../tests/muk_ai_test_helpers';

import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';
import { InsertButton } from '@muk_ai_chatter/composer/insert_button/insert_button';

defineAIModels();
describe.current.tags('muk_ai_chatter');

const DRAFT = 'Dear customer, thanks for you order.';

const SELECTION = 'thanks for you order';

const SKILLS = [
    {
        name: 'shorten',
        label: 'Shorten',
        icon: 'content_cut',
        category: 'rewrite',
        body: 'Shorten it.',
    },
    {
        name: 'grammar',
        label: 'Fix grammar',
        icon: 'spellcheck',
        category: 'fix',
        body: 'Fix it.',
    },
    {
        name: 'reply',
        label: 'Reply',
        icon: 'reply',
        category: 'generate',
        body: 'Reply to it.',
    },
];

/**
 * Stub the server the panel talks to and record what it was asked.
 * @returns {object} the calls made, and the answer and state `read` returns
 */
function mockServer() {
    const calls = {
        opened: [],
        context: [],
        sent: [],
        saved: [],
        detached: false,
        discarded: false,
        openFails: false,
        state: 'done',
        answer: 'A better sentence.',
    };
    onRpc('muk_ai.skill', 'fetch_skills', () => SKILLS);
    onRpc('muk_ai.session', 'open_for_composer', ({ kwargs }) => {
        if (calls.openFails) {
            throw new Error('no agent available');
        }
        calls.opened.push(kwargs);
        return { id: 1 };
    });
    onRpc('muk_ai.session', 'update_compose_context', ({ args }) => {
        calls.context.push({ draft: args[1], selection: args[2] });
        return true;
    });
    onRpc('muk_ai.session', 'send_message', ({ args }) => {
        calls.sent.push(args[1]);
        return { id: 1, state: 'running' };
    });
    onRpc('muk_ai.session', 'discard_unused_composer', () => (calls.discarded = true));
    onRpc('muk_ai.session', 'detach_from_composer', () => (calls.detached = true));
    onRpc('muk_ai.session', 'read', () => [
        {
            id: 1,
            last_text: calls.answer,
            state: calls.state,
            error_message: 'Boom: x',
        },
    ]);
    onRpc(
        'muk_ai.skill',
        'save_composer_prompt',
        ({ args: [label, body, category] }) => {
            calls.saved.push([label, body, category]);
            return { name: 'saved', label, body, category, icon: 'edit' };
        },
    );
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
        isAlive: () => true,
    };
}

/**
 * Hold panels that can be taken away again, as closing a composer does.
 */
class PanelHolder extends Component {
    static components = { ComposePanel };
    static template = xml`
        <t t-foreach="this.state.panels" t-as="panel" t-key="panel.id">
            <ComposePanel adapter="panel.adapter" close="() => this.close(panel)"/>
        </t>`;
    setup() {
        this.state = proxy({ panels: [] });
    }
    close(panel) {
        this.state.panels = this.state.panels.filter((entry) => entry !== panel);
    }
}

/**
 * Mount a panel over an adapter.
 * @param {string} [selection] the text the user had selected
 * @param {string} [draft] everything already written in the composer
 * @returns {Promise<{holder: PanelHolder, adapter: object}>} the fixture
 */
async function mountPanel(selection = '', draft = '') {
    const adapter = makeAdapter(selection, draft);
    const holder = await mountWithCleanup(PanelHolder);
    holder.state.panels.push({ id: 1, adapter });
    await animationFrame();
    await animationFrame();
    return { holder, adapter };
}

/**
 * Pick the first offer of the panel, opening its group when it has one.
 */
async function pickFirst() {
    if (queryFirst('.mk_compose_panel_action')) {
        await click('.mk_compose_panel_action');
        await animationFrame();
    }
    if (queryFirst('.mk_compose_panel_chips .mk_compose_panel_chip')) {
        await click('.mk_compose_panel_chips .mk_compose_panel_chip');
    }
    await animationFrame();
}

/**
 * End the run the panel waits on, as the server announces it.
 * @param {string} [state] the state the run ended in
 */
async function endRun(state = 'done') {
    await emitEvent(1, 'state', { state });
    await animationFrame();
}

test('what is offered follows what is already written', async () => {
    mockServer();
    for (const [selection, draft, actions, modifiers] of [
        ['', '', [], 3],
        [SELECTION, DRAFT, ['Fix grammar', 'Shorten'], 0],
        ['', DRAFT, ['Fix grammar', 'Shorten'], 0],
    ]) {
        const { holder } = await mountPanel(selection, draft);
        expect(queryAllTexts('.mk_compose_panel_action')).toEqual(actions);
        expect('.mk_compose_panel_quote').toHaveCount(draft ? 1 : 0);
        if (actions.length) {
            await click('.mk_compose_panel_action:last-child');
            await animationFrame();
        }
        expect('.mk_compose_panel_length').toHaveCount(modifiers);
        expect('.mk_compose_panel_tone').toHaveCount(modifiers);
        holder.state.panels = [];
        await animationFrame();
    }
});

test('the session opens with the text and the record, and a whole draft is the target', async () => {
    const calls = mockServer();
    await mountPanel('', DRAFT);
    expect(calls.opened).toMatchObject([
        {
            interface_key: 'mail_composer',
            res_model: 'res.partner',
            res_id: 7,
            draft: DRAFT,
            selection: '',
        },
    ]);
    await pickFirst();
    expect(calls.context).toEqual([{ draft: DRAFT, selection: DRAFT }]);
    expect(calls.sent).toEqual(['Fix it.']);
});

test('the chosen length and tone are carried into a message written from nothing', async () => {
    const calls = mockServer();
    await mountPanel();
    await click('.mk_compose_panel_length:last-child');
    await click('.mk_compose_panel_tone:last-child');
    await click('.mk_compose_panel_chips .mk_compose_panel_chip');
    await animationFrame();
    expect(calls.sent[0]).toBe(
        'Reply to it. Take a little more room. Write in a warm, friendly tone.',
    );
});

test('the answer streams in, and is put where the user was writing once accepted', async () => {
    const calls = mockServer();
    for (const [selection, draft, answer, applied, text = answer] of [
        [SELECTION, DRAFT, 'thank you for your order', 'selection'],
        [` ${SELECTION} `, DRAFT, 'thank you', 'selection', ' thank you '],
        ['', DRAFT, 'Dear customer, thank you.', 'replaced'],
        ['', '', 'A fresh message.', 'draft'],
    ]) {
        calls.answer = answer;
        const { holder, adapter } = await mountPanel(selection, draft);
        await pickFirst();
        await emitEvent(1, 'text_delta', { delta: 'Half ' });
        expect('.mk_compose_panel_stream').toHaveText('Half');
        await endRun();
        expect('.mk_compose_panel_diff').toHaveCount(draft ? 1 : 0);
        expect(adapter.applied).toEqual([]);
        await click('.mk_compose_panel_accept');
        await animationFrame();
        expect(adapter.applied).toEqual([[applied, text]]);
        expect(holder.state.panels).toHaveLength(0);
    }
});

test('a discarded answer never reaches the composer', async () => {
    mockServer();
    const { adapter } = await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    await endRun();
    await click('.mk_compose_panel_discard');
    await animationFrame();
    expect('.mk_compose_panel_action').toHaveCount(2);
    expect(adapter.applied).toEqual([]);
});

test('a run that fails or answers nothing says so', async () => {
    const calls = mockServer();
    await mountPanel(SELECTION, DRAFT);
    calls.state = 'error';
    await pickFirst();
    await endRun('error');
    expect('.mk_compose_panel_error').toHaveText('Boom');
    Object.assign(calls, { state: 'done', answer: '' });
    await pickFirst();
    await endRun();
    expect('.mk_compose_panel_error').toHaveText('The agent returned nothing.');
});

test('a done announced from the middle of a run is not taken as the answer', async () => {
    const calls = mockServer();
    calls.state = 'running';
    await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    await endRun();
    expect('.mk_compose_panel_busy').toHaveCount(1);
    calls.state = 'done';
    await emitEvent(1, 'state', { state: 'running' });
    await endRun();
    expect('.mk_compose_panel_accept').toHaveCount(1);
});

test('only a helper nobody asked anything is dropped when the panel closes', async () => {
    const calls = mockServer();
    const first = await mountPanel(SELECTION, DRAFT);
    first.holder.state.panels = [];
    await animationFrame();
    expect(calls.discarded).toBe(true);
    calls.discarded = false;
    const second = await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    second.holder.state.panels = [];
    await animationFrame();
    expect(calls.discarded).toBe(false);
});

test('the chips still work after the session failed to open', async () => {
    const calls = mockServer();
    calls.openFails = true;
    await mountPanel(SELECTION, DRAFT);
    expect('.mk_compose_panel_error').toHaveCount(1);
    calls.openFails = false;
    await pickFirst();
    expect(calls.sent).toEqual(['Fix it.']);
});

test('a second helper closes the one already open', async () => {
    mockServer();
    const { holder } = await mountPanel(SELECTION, DRAFT);
    holder.state.panels.push({ id: 2, adapter: makeAdapter() });
    await animationFrame();
    await animationFrame();
    expect('.mk_compose_panel').toHaveCount(1);
    expect(holder.state.panels[0].id).toBe(2);
});

test('the chat window takes the session over, and puts its answers back', async () => {
    const calls = mockServer();
    const { holder, adapter } = await mountPanel(SELECTION, DRAFT);
    await click('.mk_compose_panel_chat');
    await animationFrame();
    const chat = getService(AIChatPlugin);
    expect(calls.detached).toBe(true);
    expect(chat.windowIds).toEqual([1]);
    expect(holder.state.panels).toHaveLength(0);
    await mountWithCleanup(InsertButton, {
        props: { session: chat.session(1), text: 'From the chat' },
    });
    await click('.mk_msg_insert');
    expect(adapter.applied).toEqual([['selection', 'From the chat']]);
    expect(chat.windowIds).toEqual([]);
});

test('a free-text ask that worked can be kept as a quick action', async () => {
    const calls = mockServer();
    for (const [draft, category] of [
        ['', 'generate'],
        [DRAFT, 'rewrite'],
    ]) {
        const { holder } = await mountPanel('', draft);
        await contains('.mk_compose_panel_custom').edit('Chase the payment');
        await animationFrame();
        await endRun();
        await click('.mk_compose_panel_save_open');
        await animationFrame();
        await contains('.mk_compose_panel_save_label').edit('Chase');
        await animationFrame();
        expect(calls.saved.at(-1)).toEqual(['Chase', 'Chase the payment', category]);
        expect('.mk_compose_panel_saved').toHaveCount(1);
        holder.state.panels = [];
        await animationFrame();
    }
    await mountPanel(SELECTION, DRAFT);
    await pickFirst();
    await endRun();
    expect('.mk_compose_panel_save_open').toHaveCount(0);
});

test('a quick action can be written from scratch, and escape folds the form', async () => {
    const calls = mockServer();
    await mountPanel();
    await click('.mk_compose_panel_new');
    await animationFrame();
    await contains('.mk_compose_panel_create_label').edit('Thank them');
    await contains('.mk_compose_panel_create_body').edit('Thank the customer.');
    await click('.mk_compose_panel_create_confirm');
    await animationFrame();
    expect(calls.saved).toEqual([['Thank them', 'Thank the customer.', 'generate']]);
    await click('.mk_compose_panel_new');
    await animationFrame();
    await click('.mk_compose_panel_create_label');
    await press('Escape');
    await animationFrame();
    expect('.mk_compose_panel_create').toHaveCount(0);
    expect('.mk_compose_panel').toHaveCount(1);
});
