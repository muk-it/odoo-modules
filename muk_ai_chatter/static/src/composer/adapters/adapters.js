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
    const draftOf = () => (textarea ? textarea.value : composer.text || '');
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
    const setText = (text, caret) => {
        composer.text = text;
        if (textarea) {
            textarea.value = text;
            textarea.focus();
            textarea.setSelectionRange(caret, caret);
            textarea.dispatchEvent(new InputEvent('input', { bubbles: true }));
        }
    };
    return {
        interfaceKey: 'mail_composer',
        getDraft: draftOf,
        getSelection: () => picked?.text || '',
        applySelection(text) {
            const draft = draftOf();
            const at = locate(draft);
            if (at === -1) {
                return this.applyDraft(text);
            }
            setText(
                draft.slice(0, at) + text + draft.slice(at + picked.text.length),
                at + text.length,
            );
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
        getRecord() {
            const thread = composer.thread || composer.message?.thread;
            return { resModel: thread?.model || false, resId: thread?.id || false };
        },
        isAlive: () => !textarea || textarea.isConnected,
    };
}

/**
 * Drive a rich-text editor: the full mail composer, or a mail html field.
 *
 * Draft and selection are read when the helper opens, since the panel takes
 * the focus. The draft ends at the signature, so a reply's quoted history and
 * the sender's signature are neither read nor replaced. Every insertion is one
 * undoable step, replacing the selection the cursor was restored to.
 *
 * @param {object} plugin the editor plugin offering the helper
 * @param {{resModel: string|false, resId: number|false}} record what is written about
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeEditorAdapter(plugin, record) {
    const { selection, dom, history } = plugin.dependencies;
    const selected = plugin.document.getSelection()?.toString() || '';
    const cursor = selection.preserveSelection();
    const draftEnd = () => {
        const nodes = [...(plugin.editable?.childNodes || [])];
        let signature = plugin.editable?.querySelector('.o-signature-container');
        while (signature && signature.parentNode !== plugin.editable) {
            signature = signature.parentNode;
        }
        return { nodes, end: signature ? nodes.indexOf(signature) : nodes.length };
    };
    const insert = (text) => {
        dom.insert(asFragment(plugin.document, text));
        history.addStep();
    };
    const atCursor = (text) => {
        cursor.restore();
        insert(text);
    };
    return {
        interfaceKey: selected ? 'text_select' : 'html_field',
        getDraft() {
            const { nodes, end } = draftEnd();
            return nodes
                .slice(0, end)
                .map((node) => node.textContent || '')
                .join('');
        },
        getSelection: () => selected,
        applySelection: atCursor,
        applyDraft: atCursor,
        replaceDraft(text) {
            const { nodes, end } = draftEnd();
            const last = nodes[end - 1];
            selection.setSelection({
                anchorNode: plugin.editable,
                anchorOffset: 0,
                focusNode: last || plugin.editable,
                focusOffset: last ? last.childNodes.length || last.length || 0 : 0,
            });
            insert(text);
        },
        getRecord: () => record,
        isAlive: () => Boolean(plugin.editable?.isConnected),
    };
}

/**
 * Turn generated text into paragraphs: a blank line starts one, a single
 * newline breaks the line inside it.
 * @param {Document} document the editor's document
 * @param {string} text what the agent wrote
 * @returns {DocumentFragment|string} nodes to insert, or the text when it is one line
 */
function asFragment(document, text) {
    if (!text.includes('\n')) {
        return text;
    }
    const fragment = document.createDocumentFragment();
    for (const block of text.split(/\n{2,}/).filter((block) => block.trim())) {
        const paragraph = document.createElement('p');
        block
            .trim()
            .split('\n')
            .forEach((line, index) => {
                if (index) {
                    paragraph.append(document.createElement('br'));
                }
                paragraph.append(document.createTextNode(line));
            });
        fragment.append(paragraph);
    }
    return fragment;
}
