/** @odoo-module */

import { OdooEditor } from '@web_editor/js/editor/odoo-editor/src/OdooEditor';
import { setSelection } from '@web_editor/js/editor/odoo-editor/src/utils/utils';
import { registerCleanup } from '@web/../tests/helpers/cleanup';
import { getFixture } from '@web/../tests/helpers/utils';

import {
    makeEditorAdapter,
    makeTextComposerAdapter,
} from '@muk_ai_chatter/composer/adapters/adapters';

QUnit.module('adapters');

const DRAFT = 'Dear customer, thanks for you order.';

const SELECTION = 'thanks for you order';

const REWRITE = 'thank you for your order';

/**
 * Put a composer textarea in the fixture and drive an adapter over it.
 * @param {number[]} [range] the offsets the user had selected, none when omitted
 * @param {string} [text] what is written in the composer
 * @returns {{adapter: object, textarea: HTMLTextAreaElement, composer: object}} the fixture
 */
function makeFixture(range = null, text = DRAFT) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    getFixture().append(textarea);
    textarea.setSelectionRange(...(range || [text.length, text.length]));
    const composer = {
        textInputContent: text,
        thread: { model: 'res.partner', id: 7 },
    };
    return { adapter: makeTextComposerAdapter(composer, textarea), textarea, composer };
}

QUnit.test('the selection is the part of the draft the user had picked', (assert) => {
    const { adapter } = makeFixture([15, 35]);
    assert.strictEqual(adapter.getSelection(), SELECTION);
    assert.strictEqual(adapter.getDraft(), 'Dear customer, [[thanks for you order]].');
    assert.deepEqual(adapter.getRecord(), { resModel: 'res.partner', resId: 7 });
});

QUnit.test(
    'the rewrite finds the selection again, wherever the draft moved it',
    (assert) => {
        for (const [prefix, caret] of [
            ['', 0],
            ['PS. ', 0],
        ]) {
            const { adapter, textarea, composer } = makeFixture([15, 35]);
            textarea.value = `${prefix}${DRAFT}`;
            textarea.setSelectionRange(caret, caret);
            adapter.applySelection(REWRITE);
            assert.strictEqual(
                textarea.value,
                `${prefix}Dear customer, thank you for your order.`,
            );
            assert.strictEqual(composer.textInputContent, textarea.value);
        }
    },
);

QUnit.test(
    'a selection deleted while the panel was open is inserted, not duplicated',
    (assert) => {
        const { adapter, textarea } = makeFixture([15, 35]);
        textarea.value = 'Dear customer, ';
        textarea.setSelectionRange(15, 15);
        adapter.applySelection(REWRITE);
        assert.strictEqual(textarea.value, `Dear customer, ${REWRITE}`);
    },
);

QUnit.test('a message written from nothing lands at the caret', (assert) => {
    const { adapter, textarea } = makeFixture(null, 'Hi  - see you.');
    textarea.setSelectionRange(3, 3);
    adapter.applyDraft('there');
    assert.strictEqual(textarea.value, 'Hi there - see you.');
});

QUnit.test('a rewritten draft replaces everything that was written', (assert) => {
    const { adapter, textarea } = makeFixture();
    adapter.replaceDraft('Dear customer, thank you for your order.');
    assert.strictEqual(textarea.value, 'Dear customer, thank you for your order.');
    assert.strictEqual(textarea.selectionStart, textarea.value.length);
});

/**
 * Open a real editor over the given content and drive the helper's adapter.
 * @param {string} html what the editor holds, `[` and `]` marking the selection
 * @returns {{adapter: object, editor: OdooEditor}} the adapter and its editor
 */
function editorFixture(html) {
    const editable = document.createElement('div');
    editable.innerHTML = html;
    getFixture().append(editable);
    const editor = new OdooEditor(editable, { document });
    registerCleanup(() => editor.destroy());
    const points = [];
    const walker = document.createTreeWalker(editable, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        const node = walker.currentNode;
        for (const mark of '[]') {
            const at = node.textContent.indexOf(mark);
            if (at !== -1) {
                node.textContent = node.textContent.replace(mark, '');
                points.push([node, at]);
            }
        }
    }
    if (points.length === 2) {
        setSelection(...points[0], ...points[1]);
    }
    const adapter = makeEditorAdapter(editor, { resModel: 'res.partner', resId: 7 });
    return { adapter, editor };
}

QUnit.test(
    'the draft of a rich composer is its cleaned HTML, the selection marked',
    (assert) => {
        for (const [html, draft, selected] of [
            ['<p>Hello <b>there</b></p>', '<p>Hello <b>there</b></p>', ''],
            ['<p><br></p><p><br></p>', '', ''],
            [
                '<table><tbody><tr><td style="text-align: right;">40</td></tr></tbody></table>',
                '<table><tbody><tr><td style="text-align: right;">40</td></tr></tbody></table>',
                '',
            ],
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
            const { adapter } = editorFixture(html);
            assert.strictEqual(adapter.getDraft(), draft);
            assert.strictEqual(adapter.getSelection(), selected);
            assert.strictEqual(
                adapter.interfaceKey,
                selected ? 'text_select' : 'html_field',
            );
            document.getSelection().removeAllRanges();
        }
    },
);

QUnit.test(
    'an answer replaces the draft unfenced and sanitized, in one undoable step',
    (assert) => {
        const { adapter, editor } = editorFixture(
            '<p>Hello there</p><ol><li>old</li></ol>',
        );
        adapter.replaceDraft(
            '```html\n<html><body><p>Hi <b>Anna</b><img src="x" onerror="alert(1)">' +
                '<script>alert(2)</script></p><ul><li>one</li></ul></body></html>\n```',
        );
        const { editable } = editor;
        assert.strictEqual(editable.querySelector('b').textContent, 'Anna');
        assert.strictEqual(editable.querySelector('ul li').textContent, 'one');
        assert.containsNone(editable, 'ol, script, [onerror]');
        assert.notOk(/```|html>/.test(editable.textContent));
        editor.historyUndo();
        assert.strictEqual(
            editable.innerHTML,
            '<p>Hello there</p><ol><li>old</li></ol>',
        );
    },
);

QUnit.test(
    'a template that wraps its signature is read and replaced up to it',
    (assert) => {
        const { adapter, editor } = editorFixture(
            '<div data-o-mail-quote-container="1"><p>Your quotation is ready.</p>' +
                '<div data-o-mail-quote="1">--<br>Mitchell Admin</div></div>',
        );
        assert.ok(adapter.getDraft().includes('Your quotation is ready.'));
        assert.notOk(adapter.getDraft().includes('Mitchell Admin'));
        adapter.replaceDraft('<p>Your quotation for two desks is ready.</p>');
        assert.ok(
            /^Your quotation for two desks is ready\.\s*--\s*Mitchell Admin$/.test(
                editor.editable.textContent.trim(),
            ),
            editor.editable.innerHTML,
        );
    },
);

QUnit.test(
    'a one-paragraph answer fills the selection inside its paragraph',
    (assert) => {
        const { adapter, editor } = editorFixture('<p>Dear [customer], thanks</p>');
        adapter.applySelection(' <p><b>valued</b> client</p>');
        assert.containsOnce(editor.editable, 'p');
        assert.strictEqual(
            editor.editable.querySelector('p').innerHTML,
            'Dear <b>valued</b> client, thanks',
        );
    },
);

QUnit.test(
    'an answer lands at the end of the last paragraph without a cursor',
    (assert) => {
        document.getSelection().removeAllRanges();
        const { adapter, editor } = editorFixture('<p>Hi</p>');
        assert.strictEqual(adapter.interfaceKey, 'html_field');
        adapter.applyDraft(' you');
        assert.strictEqual(editor.editable.childNodes.length, 1);
        assert.strictEqual(editor.editable.firstChild.textContent, 'Hi you');
    },
);

QUnit.test('an answer is previewed sanitized and compared as words', (assert) => {
    const { adapter } = editorFixture('<p>Hello</p>');
    assert.strictEqual(
        String(adapter.toHtml('<p>Hi<img src="x" onerror="alert(1)"></p><p>you</p>')),
        '<p>Hi<img src="x"></p><p>you</p>',
    );
    assert.strictEqual(
        adapter.toText('<p>Dear Anna,</p><ul><li>one</li><li>two</li></ul>'),
        'Dear Anna, one two',
    );
});
