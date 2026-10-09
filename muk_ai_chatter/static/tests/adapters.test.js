import { describe, expect, getFixture, test } from '@odoo/hoot';

import { setupEditor } from '@html_editor/../tests/_helpers/editor';
import { MAIN_PLUGINS } from '@html_editor/plugin_sets';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import {
    makeEditorAdapter,
    makeTextComposerAdapter,
} from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposeAIPlugin } from '@muk_ai_chatter/composer/editor_plugin/editor_plugin';

describe.current.tags('muk_ai_chatter');
defineMailModels();

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
    const composer = {
        text,
        thread: { model: 'res.partner', id: 7 },
    };
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
    const { adapter, textarea } = makeFixture(null, 'Hi  - see you.');
    textarea.setSelectionRange(3, 3);
    adapter.applyDraft('there');
    expect(textarea.value).toBe('Hi there - see you.');
});

test('a rewritten draft replaces everything that was written', () => {
    const { adapter, textarea } = makeFixture();
    adapter.replaceDraft('Dear customer, thank you for your order.');
    expect(textarea.value).toBe('Dear customer, thank you for your order.');
    expect(textarea.selectionStart).toBe(textarea.value.length);
});

const SIGNATURE =
    '<div class="o-signature-container" data-o-mail-quote-container="1" contenteditable="false">' +
    '<div data-o-mail-quote="1">-- <br><div contenteditable="true">' +
    '<div data-o-mail-quote="1" class="o-paragraph">Mitchell Admin</div></div></div></div>';

/**
 * Open a real editor over the given content and drive the helper's adapter.
 * @param {string} html what the editor holds before the signature
 * @param {string} [after] what follows the signature, a quoted reply
 * @returns {Promise<{adapter: object, el: HTMLElement}>} the adapter and editable
 */
async function editorFixture(html, after = '') {
    const { el, plugins } = await setupEditor(`${html}${SIGNATURE}${after}`, {
        config: { Plugins: [...MAIN_PLUGINS, ComposeAIPlugin] },
    });
    const adapter = makeEditorAdapter(plugins.get('mukAiCompose'), {
        resModel: 'res.partner',
        resId: 7,
    });
    return { adapter, el };
}

test('the draft of a rich composer ends at the signature', async () => {
    for (const [html, draft] of [
        ['<p>Hello there</p>', 'Hello there'],
        ['<p><br></p>', ''],
    ]) {
        const { adapter } = await editorFixture(html, '<p>On Monday you wrote...</p>');
        expect(adapter.getDraft().trim()).toBe(draft);
    }
});

test('a rewritten message replaces the draft and keeps the signature under it', async () => {
    const { adapter, el } = await editorFixture(
        '<p>Hello there</p><p><br></p>',
        '<p>On Monday you wrote...</p>',
    );
    adapter.replaceDraft('Good day to you.\n\nKind regards');
    expect(adapter.getDraft()).toBe('Good day to you.Kind regards');
    const signature = el.querySelector('.o-signature-container');
    expect(signature).toHaveText(/--\s*Mitchell Admin/);
    expect(signature.previousElementSibling).toHaveText('Kind regards');
    expect(el.lastElementChild).toHaveText('On Monday you wrote...');
});
