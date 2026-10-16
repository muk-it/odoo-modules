/** @odoo-module */

import { OdooEditor } from '@web_editor/js/editor/odoo-editor/src/OdooEditor';
import { setSelection } from '@web_editor/js/editor/odoo-editor/src/utils/utils';
import { registerCleanup } from '@web/../tests/helpers/cleanup';
import { getFixture } from '@web/../tests/helpers/utils';

import {
    makeEditorAdapter,
    makeTextComposerAdapter,
} from '@muk_ai_chatter/composer/adapters/adapters';

QUnit.module('muk_ai_chatter', {}, function () {
    QUnit.module('adapters');

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
        const composer = { activeThread: { model: 'res.partner', id: 7 } };
        return { adapter: makeTextComposerAdapter(composer, textarea), textarea };
    }

    QUnit.test(
        'the selection is the part of the draft the user had picked',
        (assert) => {
            const { adapter } = makeFixture([15, 35]);
            assert.strictEqual(adapter.getSelection(), SELECTION);
            assert.strictEqual(
                adapter.getDraft(),
                'Dear customer, [[thanks for you order]].',
            );
            assert.deepEqual(adapter.getRecord(), {
                resModel: 'res.partner',
                resId: 7,
            });
        },
    );

    QUnit.test(
        'the rewrite finds the selection again, wherever the draft moved it',
        (assert) => {
            for (const [prefix, caret] of [
                ['', 0],
                ['PS. ', 0],
            ]) {
                const { adapter, textarea } = makeFixture([15, 35]);
                textarea.value = `${prefix}${DRAFT}`;
                textarea.setSelectionRange(caret, caret);
                adapter.applySelection(REWRITE);
                assert.strictEqual(
                    textarea.value,
                    `${prefix}Dear customer, thank you for your order.`,
                );
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
     * @param {string} html what the editor holds
     * @param {Function} [select] puts the cursor where the user left it
     * @returns {{adapter: object, editor: OdooEditor}} the adapter and its editor
     */
    function editorFixture(html, select = null) {
        const editable = document.createElement('div');
        editable.innerHTML = html;
        getFixture().append(editable);
        const editor = new OdooEditor(editable, { document });
        registerCleanup(() => editor.destroy());
        select?.(editable);
        const adapter = makeEditorAdapter(editor, {
            resModel: 'res.partner',
            resId: 7,
        });
        return { adapter, editor };
    }

    /**
     * Select what the user marked between [ and ] in the editor's content.
     * @param {HTMLElement} editable the editor's root
     */
    function selectMarked(editable) {
        const walker = document.createTreeWalker(editable, NodeFilter.SHOW_TEXT);
        const ends = [];
        while (walker.nextNode()) {
            const node = walker.currentNode;
            for (const mark of ['[', ']']) {
                const at = node.textContent.indexOf(mark);
                if (at !== -1) {
                    node.textContent = node.textContent.replace(mark, '');
                    ends.push([node, at]);
                }
            }
        }
        setSelection(...ends[0], ...ends[1]);
    }

    QUnit.test('the draft of a rich composer is its cleaned HTML', (assert) => {
        for (const [html, draft] of [
            ['<p>Hello <b>there</b></p>', '<p>Hello <b>there</b></p>'],
            ['<p><br></p><p><br></p>', ''],
            [
                '<table><tbody><tr><td style="text-align: right;">40</td></tr></tbody></table>',
                '<table><tbody><tr><td style="text-align: right;">40</td></tr></tbody></table>',
            ],
        ]) {
            const { adapter } = editorFixture(html);
            assert.strictEqual(adapter.interfaceKey, 'html_field');
            assert.strictEqual(adapter.getDraft(), draft);
        }
    });

    QUnit.test(
        'the selection is marked where it sits, across formatting and in a cell',
        (assert) => {
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
                const { adapter } = editorFixture(html, selectMarked);
                assert.strictEqual(adapter.interfaceKey, 'text_select');
                assert.strictEqual(adapter.getDraft(), marked);
                assert.strictEqual(adapter.getSelection(), selected);
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
                '\x60\x60\x60html\n<html><body><p>Hi <b>Anna</b><img src="x" onerror="alert(1)">' +
                    '<script>alert(2)</script></p><ul><li>one</li></ul></body></html>\n\x60\x60\x60',
            );
            const { editable } = editor;
            assert.strictEqual(editable.querySelector('b').textContent, 'Anna');
            assert.strictEqual(editable.querySelector('ul li').textContent, 'one');
            assert.containsNone(editable, 'ol, script, [onerror]');
            assert.notOk(/\x60{3}|html>/.test(editable.textContent));
            editor.historyUndo();
            assert.strictEqual(
                adapter.getDraft(),
                '<p>Hello there</p><ol><li>old</li></ol>',
            );
        },
    );

    QUnit.test(
        'a one-paragraph answer fills the selection inside its paragraph',
        (assert) => {
            const { adapter, editor } = editorFixture(
                '<p>Dear [customer], thanks</p>',
                selectMarked,
            );
            adapter.applySelection('<p><b>valued</b> client</p>');
            assert.containsOnce(editor.editable, 'p');
            assert.strictEqual(
                editor.editable.querySelector('p').innerHTML,
                'Dear <b>valued</b> client, thanks',
            );
        },
    );

    QUnit.test('an answer is previewed sanitized and compared as words', (assert) => {
        const { adapter } = editorFixture('<p>Hello</p>');
        assert.strictEqual(
            String(
                adapter.toHtml('<p>Hi<img src="x" onerror="alert(1)"></p><p>you</p>'),
            ),
            '<p>Hi<img src="x"></p><p>you</p>',
        );
        assert.strictEqual(
            adapter.toText('<p>Dear Anna,</p><ul><li>one</li><li>two</li></ul>'),
            'Dear Anna, one two',
        );
    });

    QUnit.test(
        'an answer lands at the cursor, or at the end when there was none',
        (assert) => {
            const { adapter: atCursor, editor } = editorFixture(
                '<p>Hi friend</p>',
                (editable) => {
                    const text = editable.firstChild.firstChild;
                    setSelection(text, 3, text, 9);
                },
            );
            assert.strictEqual(atCursor.getSelection(), 'friend');
            assert.strictEqual(atCursor.interfaceKey, 'text_select');
            atCursor.applySelection('there');
            assert.strictEqual(
                editor.editable.textContent.replace(' ', ' '),
                'Hi there',
            );
            document.getSelection().removeAllRanges();
            const { adapter: atEnd, editor: other } = editorFixture('<p>Hi</p>');
            assert.strictEqual(atEnd.interfaceKey, 'html_field');
            atEnd.applyDraft(' you');
            assert.strictEqual(other.editable.textContent, 'Hi you');
            const { adapter: blank, editor: empty } = editorFixture('<p><br></p>');
            blank.applyDraft('<p>Hi</p><ul><li>you</li></ul>');
            assert.strictEqual(
                empty.editable.innerHTML,
                '<p>Hi</p><ul><li>you</li></ul>',
            );
        },
    );
});
