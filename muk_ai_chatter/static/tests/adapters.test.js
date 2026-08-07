import { describe, expect, getFixture, test } from '@odoo/hoot';

import {
    makeEditorAdapter,
    makeTextComposerAdapter,
} from '@muk_ai_chatter/composer/adapters';

describe.current.tags('muk_ai_chatter');

const DRAFT = 'Dear customer, thanks for you order.';

const SELECTION = 'thanks for you order';

const REWRITE = 'thank you for your order';

/**
 * Put a composer textarea in the fixture and drive an adapter over it.
 * @param {number[]} [range] the offsets the user had selected, none when omitted
 * @param {string} [text] what is written in the composer
 * @returns {{adapter: object, textarea: HTMLTextAreaElement}} the fixture
 */
function makeFixture(range = null, text = DRAFT) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    getFixture().append(textarea);
    textarea.setSelectionRange(...(range || [text.length, text.length]));
    const composer = { text, targetThread: { model: 'res.partner', id: 7 } };
    return { adapter: makeTextComposerAdapter(composer, textarea), textarea };
}

test('the selection is the part of the draft the user had picked', () => {
    const { adapter } = makeFixture([15, 35]);
    expect(adapter.getSelection()).toBe(SELECTION);
    expect(adapter.getDraft()).toBe(DRAFT);
});

test('the rewrite replaces the selection after the caret moved away', () => {
    const { adapter, textarea } = makeFixture([15, 35]);
    textarea.setSelectionRange(0, 0);
    adapter.applySelection(REWRITE);
    expect(textarea.value).toBe('Dear customer, thank you for your order.');
});

test('the rewrite follows the selected text when the draft shifted', () => {
    const { adapter, textarea } = makeFixture([15, 35]);
    textarea.value = `PS. ${DRAFT}`;
    adapter.applySelection(REWRITE);
    expect(textarea.value).toBe('PS. Dear customer, thank you for your order.');
});

test('a selection deleted while the panel was open is inserted, not duplicated', () => {
    const { adapter, textarea } = makeFixture([15, 35]);
    textarea.value = 'Dear customer, ';
    textarea.setSelectionRange(15, 15);
    adapter.applySelection(REWRITE);
    expect(textarea.value).toBe(`Dear customer, ${REWRITE}`);
});

test('a message written from nothing lands at the caret', () => {
    const { adapter, textarea } = makeFixture(null, 'Hi  — see you.');
    textarea.setSelectionRange(3, 3);
    adapter.applyDraft('there');
    expect(textarea.value).toBe('Hi there — see you.');
});

test('a rewritten draft replaces everything that was written', () => {
    const { adapter, textarea } = makeFixture();
    adapter.replaceDraft('Dear customer, thank you for your order.');
    expect(textarea.value).toBe('Dear customer, thank you for your order.');
    expect(textarea.selectionStart).toBe(textarea.value.length);
});

test('the record the composer writes about is what the helper is told', () => {
    const { adapter } = makeFixture();
    expect(adapter.getRecord()).toEqual({ resModel: 'res.partner', resId: 7 });
    expect(adapter.interfaceKey).toBe('mail_composer');
});

/**
 * Put an editable in the fixture and drive an editor adapter over it.
 * @param {string} html what the editor holds, signature included
 * @returns {{adapter: object, plugin: object}} the fixture
 */
function makeEditorFixture(html) {
    const editable = document.createElement('div');
    editable.innerHTML = html;
    getFixture().append(editable);
    const plugin = {
        editable,
        document,
        dependencies: {
            selection: {
                preserveSelection: () => ({ restore: () => {} }),
                setSelection: (spec) => {
                    plugin.picked = spec;
                },
            },
            dom: { insert: () => {} },
            history: { addStep: () => {} },
        },
    };
    const record = { resModel: 'res.partner', resId: 7 };
    return { adapter: makeEditorAdapter(plugin, record), plugin };
}

const SIGNED = '<p>Hello there</p><div class="o-signature-container">-- Admin</div>';

test('the signature the composer opens with is not a draft', () => {
    const { adapter } = makeEditorFixture(SIGNED);
    expect(adapter.getDraft().trim()).toBe('Hello there');
});

test('a composer holding only a signature has nothing written in it', () => {
    const { adapter } = makeEditorFixture(
        '<p><br></p><div class="o-signature-container">-- Admin</div>',
    );
    expect(adapter.getDraft().trim()).toBe('');
});

test('replacing the message leaves the signature under it', () => {
    const { adapter, plugin } = makeEditorFixture(SIGNED);
    adapter.replaceDraft('Good day to you.');
    expect(plugin.picked.focusOffset).toBe(1);
});

test('a message with no signature is replaced whole', () => {
    const { adapter, plugin } = makeEditorFixture('<p>One</p><p>Two</p>');
    adapter.replaceDraft('Something else.');
    expect(plugin.picked.focusOffset).toBe(2);
});

test('what sits under the signature is not part of the draft', () => {
    const { adapter } = makeEditorFixture(`${SIGNED}<p>On Monday you wrote…</p>`);
    expect(adapter.getDraft().trim()).toBe('Hello there');
});

test('a rewrite never lands above text it also rewrote', () => {
    const { adapter, plugin } = makeEditorFixture(
        `${SIGNED}<p>On Monday you wrote…</p>`,
    );
    adapter.replaceDraft('Good day to you.');
    expect(plugin.picked.focusOffset).toBe(1);
});
