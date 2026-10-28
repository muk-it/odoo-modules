import { markup } from '@odoo/owl';

const ZERO_WIDTH = /[\u200B\uFEFF]/g;

const FENCE = /^\s*```[^\n]*\n?|\n?```\s*$/g;

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
 * text should the user keep typing meanwhile.
 *
 * @param {import("models").Composer} composer the composer record
 * @param {HTMLTextAreaElement} textarea the input the user types in
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeTextComposerAdapter(composer, textarea) {
    const draftOf = () => (textarea ? textarea.value : composer.composerText || '');
    const start = textarea?.selectionStart ?? 0;
    const end = textarea?.selectionEnd ?? 0;
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
        composer.composerText = text;
        if (textarea) {
            textarea.value = text;
            textarea.focus();
            textarea.setSelectionRange(caret, caret);
            textarea.dispatchEvent(new InputEvent('input', { bubbles: true }));
        }
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
            const caret = textarea?.selectionStart ?? draft.length;
            setText(
                draft.slice(0, caret) + text + draft.slice(caret),
                caret + text.length,
            );
        },
        replaceDraft: (text) => setText(text, text.length),
        toHtml: (text) => text,
        toText: (text) => text,
        getRecord: () => ({
            resModel: composer.targetThread?.model || false,
            resId: composer.targetThread?.id || false,
        }),
        isAlive: () => !textarea || textarea.isConnected,
    };
}

/**
 * Drive a rich-text editor: the full mail composer, or a mail html field.
 *
 * The draft is read as cleaned HTML when the helper opens, the selection marked
 * where it sits, and ends at the signature or the quoted thread, however deep a
 * template nests them, so neither is read nor replaced. An answer is sanitized and
 * inserted as one undoable step, replacing the selection the cursor was
 * restored to.
 *
 * @param {object} plugin the editor plugin offering the helper
 * @param {{resModel: string|false, resId: number|false}} record what is written about
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeEditorAdapter(plugin, record) {
    const { baseContainer, dom, history, sanitize, selection } = plugin.dependencies;
    const picked = selection.getEditableSelection();
    const cursor = selection.preserveSelection();
    const upToSignature = (root) => {
        const range = new Range();
        range.selectNodeContents(root);
        const signature = root.querySelector(
            '.o-signature-container, [data-o-mail-quote]',
        );
        if (signature) {
            range.setEndBefore(signature);
        }
        return range;
    };
    const clean = (root) => {
        plugin.dispatchTo('clean_for_save_handlers', { root });
        return root.innerHTML.trim();
    };
    const twin = (node) =>
        node === plugin.editable
            ? draft
            : twin(node.parentNode).childNodes[
                  [...node.parentNode.childNodes].indexOf(node)
              ];
    const range = new Range();
    range.setStart(picked.startContainer, picked.startOffset);
    range.setEnd(picked.endContainer, picked.endOffset);
    const quoted = range.toString().replace(ZERO_WIDTH, '');
    const draft = plugin.editable.cloneNode(true);
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
    draft.replaceChildren(upToSignature(draft).cloneContents());
    const marked = draft.textContent.trim() ? clean(draft) : '';
    const fragmentOf = (text) => {
        const { body } = new DOMParser().parseFromString(
            `<body>${text.replace(FENCE, '')}`,
            'text/html',
        );
        sanitize.sanitize(body);
        const only = body.children.length === 1 && body.firstElementChild;
        if (only?.tagName === 'P') {
            only.replaceWith(...only.childNodes);
        }
        const fragment = plugin.document.createDocumentFragment();
        fragment.append(...body.childNodes);
        return fragment;
    };
    const insert = (text) => {
        dom.insert(fragmentOf(text));
        history.addStep();
    };
    const atCursor = (text) => {
        cursor.restore();
        insert(text);
    };
    return {
        interfaceKey: quoted ? 'text_select' : 'html_field',
        getDraft: () => marked,
        getSelection: () => quoted,
        applySelection: atCursor,
        applyDraft: atCursor,
        replaceDraft(text) {
            const range = upToSignature(plugin.editable);
            range.deleteContents();
            const container = baseContainer.createBaseContainer();
            range.insertNode(container);
            selection.setSelection({ anchorNode: container, anchorOffset: 0 });
            insert(text);
        },
        toHtml(text) {
            const holder = plugin.document.createElement('div');
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
        isAlive: () => Boolean(plugin.editable?.isConnected),
    };
}
