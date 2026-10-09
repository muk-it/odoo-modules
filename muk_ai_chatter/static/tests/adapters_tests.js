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
            assert.strictEqual(adapter.getDraft(), DRAFT);
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

    QUnit.test(
        'a rewritten message replaces the whole draft in one undoable step',
        (assert) => {
            const { adapter, editor } = editorFixture('<p>Hello there</p><p>Bye</p>');
            assert.strictEqual(adapter.getDraft(), 'Hello thereBye');
            adapter.replaceDraft('Good day to you.\n\nKind regards');
            assert.strictEqual(
                editor.editable.innerHTML,
                '<p>Good day to you.</p><p>Kind regards</p>',
            );
            editor.historyUndo();
            assert.strictEqual(adapter.getDraft(), 'Hello thereBye');
        },
    );

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
        },
    );
});
