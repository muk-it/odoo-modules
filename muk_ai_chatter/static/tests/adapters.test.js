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
    expect(adapter.getDraft()).toBe('Dear customer, [[thanks for you order]].');
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

test('the draft of a rich composer is its cleaned HTML, up to the signature', async () => {
    for (const [html, draft] of [
        ['<p>Hello <b>there</b></p>', '<p>Hello <b>there</b></p>'],
        ['<p><br></p><p><br></p>', ''],
        [
            '<table><tbody><tr><td style="text-align: right;">40</td></tr></tbody></table>',
            '<table><tbody><tr><td style="text-align: right;">40</td></tr></tbody></table>',
        ],
    ]) {
        const { adapter } = await editorFixture(html, '<p>On Monday you wrote...</p>');
        expect(adapter.interfaceKey).toBe('html_field');
        expect(adapter.getDraft()).toBe(draft);
    }
});

test('the selection is marked where it sits, across formatting and in a cell', async () => {
    for (const [html, marked, selected] of [
        [
            '<p>Hi <b>An[na</b> and <a href="https://x.example">Jo]e</a></p>',
            '<p>Hi <b>An[[na</b> and <a href="https://x.example">Jo]]e</a></p>',
            'na and Jo',
        ],
        [
            '<table><tbody><tr><td>[black mesh]</td><td>40</td></tr></tbody></table>',
            '<table><tbody><tr><td>[[black mesh]]</td><td>40</td></tr></tbody></table>',
            'black mesh',
        ],
    ]) {
        const { plugins } = await setupEditor(html, {
            config: { Plugins: [...MAIN_PLUGINS, ComposeAIPlugin] },
        });
        const adapter = makeEditorAdapter(plugins.get('mukAiCompose'), {});
        expect(adapter.interfaceKey).toBe('text_select');
        expect(adapter.getDraft()).toBe(marked);
        expect(adapter.getSelection()).toBe(selected);
    }
});

test('an answer replaces the draft unfenced and sanitized, the signature kept', async () => {
    const { adapter, el } = await editorFixture(
        '<p>Hello there</p><ol><li>old</li></ol>',
        '<p>On Monday you wrote...</p>',
    );
    adapter.replaceDraft(
        '```html\n<html><body><p>Hi <b>Anna</b><img src="x" onerror="alert(1)">' +
            '<script>alert(2)</script></p><ul><li>one</li></ul></body></html>\n```',
    );
    expect('b').toHaveText('Anna');
    expect('ul li').toHaveText('one');
    expect('ol').toHaveCount(0);
    expect('script').toHaveCount(0);
    expect('[onerror]').toHaveCount(0);
    expect(el).not.toHaveText(/```|html>/);
    expect('.o-signature-container').toHaveText(/^--\s*Mitchell Admin$/);
    expect(el.lastElementChild).toHaveText('On Monday you wrote...');
});

test('a one-paragraph answer fills the selection inside its paragraph', async () => {
    const { el, plugins } = await setupEditor('<p>Dear [customer], thanks</p>', {
        config: { Plugins: [...MAIN_PLUGINS, ComposeAIPlugin] },
    });
    const adapter = makeEditorAdapter(plugins.get('mukAiCompose'), {});
    adapter.applySelection(' <p><b>valued</b> client</p>');
    expect(el.querySelectorAll('p')).toHaveCount(1);
    expect(el.querySelector('p')).toHaveInnerHTML('Dear <b>valued</b> client, thanks');
});

test('an answer is previewed sanitized and compared as words', async () => {
    const { adapter } = await editorFixture('<p>Hello</p>');
    expect(
        String(adapter.toHtml('<p>Hi<img src="x" onerror="alert(1)"></p><p>you</p>')),
    ).toBe('<p>Hi<img src="x"></p><p>you</p>');
    expect(adapter.toText('<p>Dear Anna,</p><ul><li>one</li><li>two</li></ul>')).toBe(
        'Dear Anna, one two',
    );
});
