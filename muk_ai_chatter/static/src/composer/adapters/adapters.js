/** @odoo-module */

import { markup } from '@odoo/owl';

import {
    preserveCursor,
    setCursorEnd,
    setSelection,
} from '@web_editor/js/editor/odoo-editor/src/utils/utils';

const ZERO_WIDTH = /[\u200B\uFEFF]/g;

const FENCE = /^\s*\x60{3}[^\n]*\n?|\n?\x60{3}\s*$/g;

/**
 * @typedef {object} ComposerAdapter
 * @property {string} interfaceKey which composer is asking, for the prompt
 * @property {() => string} getDraft everything written so far, as text
 * @property {() => string} getSelection the selected part, empty when none
 * @property {(text: string) => void} applySelection replace the selected part
 * @property {(text: string) => void} applyDraft put the text where the cursor is
 * @property {(text: string) => void} replaceDraft put the text in place of it all
 * @property {() => {resModel: string|false, resId: number|false}} getRecord
 * @property {() => boolean} isAlive whether the composer is still on screen
 * @property {(text: string) => object|string} toHtml an answer as what it inserts
 * @property {(text: string) => string} toText an answer or draft as plain words
 */

/**
 * Drive the plain-text composer of a chatter or a Discuss conversation.
 *
 * The selection is taken once, when the helper opens, and found again by its
 * text should the user keep typing meanwhile. Every change goes through the
 * textarea's input event, which hands it to the composer record.
 *
 * @param {object} composer the composer record
 * @param {HTMLTextAreaElement} textarea the input the user types in
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeTextComposerAdapter(composer, textarea) {
    const draftOf = () => textarea.value;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const picked = start === end ? null : { start, text: draftOf().slice(start, end) };
    const locate = (draft) => {
        if (!picked) {
            return -1;
        }
        const held = draft.slice(picked.start, picked.start + picked.text.length);
        return held === picked.text ? picked.start : draft.indexOf(picked.text);
    };
    const around = (draft, at, middle) =>
        draft.slice(0, at) + middle + draft.slice(at + picked.text.length);
    const setText = (text, caret) => {
        textarea.value = text;
        textarea.focus();
        textarea.setSelectionRange(caret, caret);
        textarea.dispatchEvent(new InputEvent('input', { bubbles: true }));
    };
    return {
        interfaceKey: 'mail_composer',
        getDraft() {
            const draft = draftOf();
            const at = locate(draft);
            return at === -1 ? draft : around(draft, at, `[[${picked.text}]]`);
        },
        getSelection: () => picked?.text || '',
        applySelection(text) {
            const draft = draftOf();
            const at = locate(draft);
            if (at === -1) {
                return this.applyDraft(text);
            }
            setText(around(draft, at, text), at + text.length);
        },
        applyDraft(text) {
            const draft = draftOf();
            const caret = textarea.selectionStart;
            setText(
                draft.slice(0, caret) + text + draft.slice(caret),
                caret + text.length,
            );
        },
        replaceDraft: (text) => setText(text, text.length),
        toHtml: (text) => text,
        toText: (text) => text,
        getRecord() {
            const thread = composer.activeThread;
            return { resModel: thread?.model || false, resId: thread?.id || false };
        },
        isAlive: () => textarea.isConnected,
    };
}

/**
 * Drive the editor of the full mail composer.
 *
 * The draft is read as cleaned HTML when the helper opens, the selection marked
 * where it sits, since the panel takes the focus. The signature is added when
 * the mail is sent, so the editor holds the draft alone. An answer is sanitized
 * and inserted as one undoable step, replacing the selection the cursor was
 * restored to, or landing at the end without one; an empty editor is replaced.
 *
 * @param {object} editor the OdooEditor of the composer's body
 * @param {{resModel: string|false, resId: number|false}} record what is written about
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeEditorAdapter(editor, record) {
    const { document, editable } = editor;
    const inEditable = editor.isSelectionInEditable();
    const picked = inEditable ? document.getSelection().getRangeAt(0) : null;
    const quoted = picked ? picked.toString().replace(ZERO_WIDTH, '') : '';
    const cursor = inEditable ? preserveCursor(document) : null;
    const draft = editable.cloneNode(true);
    const twin = (node) =>
        node === editable
            ? draft
            : twin(node.parentNode).childNodes[
                  [...node.parentNode.childNodes].indexOf(node)
              ];
    if (quoted) {
        for (const [node, offset, mark] of [
            [picked.endContainer, picked.endOffset, ']]'],
            [picked.startContainer, picked.startOffset, '[['],
        ]) {
            const at = new Range();
            at.setStart(twin(node), offset);
            at.insertNode(new Text(mark));
        }
    }
    editor.cleanForSave(draft);
    const marked = draft.textContent.trim() ? draft.innerHTML.trim() : '';
    const fragmentOf = (text) => {
        const inert = new DOMParser().parseFromString('', 'text/html');
        const holder = inert.createElement('div');
        holder.innerHTML = text.replace(FENCE, '');
        window.DOMPurify.sanitize(holder, { IN_PLACE: true });
        const only = holder.children.length === 1 && holder.firstElementChild;
        if (only?.tagName === 'P') {
            only.replaceWith(...only.childNodes);
        }
        const fragment = document.createDocumentFragment();
        fragment.append(...holder.childNodes);
        return fragment;
    };
    const replaceAll = (text) => {
        setSelection(editable, 0, editable, editable.childNodes.length);
        editor.execCommand('insert', fragmentOf(text));
    };
    const atCursor = (text) => {
        const blank = [...editable.childNodes].every(
            (node) => !node.textContent.trim() && !node.querySelector?.(':not(br)'),
        );
        if (blank) {
            return replaceAll(text);
        }
        if (cursor) {
            cursor();
        } else {
            setCursorEnd(editable);
        }
        editor.execCommand('insert', fragmentOf(text));
    };
    return {
        interfaceKey: quoted ? 'text_select' : 'html_field',
        getDraft: () => marked,
        getSelection: () => quoted,
        applySelection: atCursor,
        applyDraft: atCursor,
        replaceDraft: replaceAll,
        toHtml(text) {
            const holder = document.createElement('div');
            holder.append(fragmentOf(text));
            return markup(holder.innerHTML);
        },
        toText(text) {
            const fragment = fragmentOf(text);
            fragment.querySelectorAll('p, div, li, td, th, br').forEach((node) => {
                node.append(' ');
            });
            return fragment.textContent.replace(/\s+/g, ' ').trim();
        },
        getRecord: () => record,
        isAlive: () => editable.isConnected,
    };
}
