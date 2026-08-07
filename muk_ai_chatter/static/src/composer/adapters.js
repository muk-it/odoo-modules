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
 * The composer is a textarea bound to `composer.text`, so the draft is read
 * and written through that field and the cursor is the textarea's own.
 *
 * @param {import("models").Composer} composer the composer record
 * @param {HTMLTextAreaElement} textarea the input the user types in
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeTextComposerAdapter(composer, textarea) {
    // The draft and the offsets into it are both read off the textarea:
    // taking the text from one place and the offsets from another is how a
    // selection ends up cut out of the wrong string.
    const draftOf = () => (textarea ? textarea.value : composer.text || '');
    // Taken once, when the helper opens, the way the editor adapter does it:
    // the panel takes the focus, and a click back into the message collapses
    // the browser selection, so reading it again at accept time would replace
    // nothing and leave the rewrite next to the text it was meant to replace.
    const picked = (() => {
        const start = textarea?.selectionStart ?? 0;
        const end = textarea?.selectionEnd ?? 0;
        return start === end ? null : { start, text: draftOf().slice(start, end) };
    })();
    // The user keeps typing while the panel is open, so the recorded offset is
    // only trusted while it still holds what was selected.
    const locate = (draft) => {
        if (!picked) {
            return -1;
        }
        const end = picked.start + picked.text.length;
        return draft.slice(picked.start, end) === picked.text
            ? picked.start
            : draft.indexOf(picked.text);
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
            const start = locate(draft);
            if (start === -1) {
                this.applyDraft(text);
                return;
            }
            setText(
                draft.slice(0, start) + text + draft.slice(start + picked.text.length),
                start + text.length,
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
        replaceDraft(text) {
            setText(text, text.length);
        },
        getRecord: () => ({
            resModel: composer.targetThread?.model || false,
            resId: composer.targetThread?.id || false,
        }),
        isAlive: () => !textarea || textarea.isConnected,
    };
}

/**
 * Drive a rich-text editor: the full mail composer, or any html field.
 *
 * The draft and the selection are read once, when the helper is opened:
 * a panel takes the focus away from the editable, and a browser selection does
 * not survive that. The cursor is preserved the way the editor itself does it,
 * so what the user accepts lands exactly where they had selected — replacing
 * the selection, because `insert` deletes a non-collapsed one first — in a
 * single undoable step.
 *
 * @param {object} plugin the editor plugin offering the helper
 * @param {{resModel: string|false, resId: number|false}} record what is written about
 * @returns {ComposerAdapter} the adapter the writing helper drives
 */
export function makeEditorAdapter(plugin, record) {
    const { selection, dom, history } = plugin.dependencies;
    const selected = plugin.document.getSelection()?.toString() || '';
    const cursor = selection.preserveSelection();
    const insert = (text) => {
        cursor.restore();
        dom.insert(asFragment(plugin.document, text));
        history.addStep();
    };
    // The full composer opens with the sender's signature already in the
    // editable, and a reply keeps the quoted history under it. The message
    // being written is what sits above that line: counted as a draft, the
    // signature turns an empty composer into "3 words in your draft" and
    // offers to rewrite "-- Mitchell Admin". Reading and replacing share the
    // same boundary, or a rewrite lands above text it also rewrote.
    const signatureBlock = () => {
        let node = plugin.editable?.querySelector('.o-signature-container');
        while (node && node.parentNode !== plugin.editable) {
            node = node.parentNode;
        }
        return node;
    };
    const draftNodes = () => {
        const nodes = [...(plugin.editable?.childNodes || [])];
        const signature = signatureBlock();
        return { nodes, end: signature ? nodes.indexOf(signature) : nodes.length };
    };
    const draftOf = () => {
        const { nodes, end } = draftNodes();
        return nodes
            .slice(0, end)
            .map((node) => node.textContent || '')
            .join('');
    };
    return {
        interfaceKey: selected ? 'text_select' : 'html_field',
        getDraft: draftOf,
        getSelection: () => selected,
        applySelection: insert,
        applyDraft: insert,
        replaceDraft(text) {
            selection.setSelection({
                anchorNode: plugin.editable,
                anchorOffset: 0,
                focusNode: plugin.editable,
                focusOffset: draftNodes().end,
            });
            dom.insert(asFragment(plugin.document, text));
            history.addStep();
        },
        getRecord: () => record,
        isAlive: () => Boolean(plugin.editable?.isConnected),
    };
}

/**
 * Turn generated text into nodes, so its paragraphs survive the insertion.
 *
 * The editor sets a string as `textContent`, where every blank line collapses
 * into one run of whitespace — a three-paragraph message would arrive as a
 * single one.
 *
 * @param {Document} document the editor's document
 * @param {string} text what the agent wrote
 * @returns {DocumentFragment|string} nodes to insert, or the text when it is one line
 */
function asFragment(document, text) {
    const blocks = text.split(/\n{2,}/).filter((block) => block.trim());
    if (blocks.length < 2) {
        return text;
    }
    const fragment = document.createDocumentFragment();
    for (const block of blocks) {
        const paragraph = document.createElement('p');
        paragraph.textContent = block.trim();
        fragment.append(paragraph);
    }
    return fragment;
}
