/** @odoo-module */

import { _t } from '@web/core/l10n/translation';
import { usePopover } from '@web/core/popover/popover_hook';
import { patch } from '@web/core/utils/patch';
import { HtmlField } from '@web_editor/js/backend/html_field';
import { closestBlock } from '@web_editor/js/editor/odoo-editor/src/utils/utils';

import { makeEditorAdapter } from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';
import { OPEN_EVENT } from '@muk_ai_chatter/composer/composer_field/composer_field';

/**
 * Offer the writing helper in the editor of the full mail composer: a toolbar
 * button, a `/` command, and the open event the composer's footer button fires.
 */
patch(HtmlField.prototype, 'muk_ai_chatter', {
    setup() {
        this._super(...arguments);
        this.mukAiInComposer = this.props.record.resModel === 'mail.compose.message';
        if (this.mukAiInComposer) {
            this.mukAiPopover = usePopover();
            this.mukAiOpenPanel = () => this.openComposePanel();
        }
    },
    get wysiwygOptions() {
        const options = this._super();
        if (!this.mukAiInComposer) {
            return options;
        }
        return {
            ...options,
            powerboxCommands: [
                ...(options.powerboxCommands || []),
                {
                    category: _t('AI Tools'),
                    name: _t('Write with AI'),
                    description: _t('Rewrite the selection, or write from the record'),
                    fontawesome: 'fa-magic',
                    priority: 2,
                    callback: this.mukAiOpenPanel,
                },
            ],
        };
    },
    async startWysiwyg(wysiwyg) {
        await this._super(...arguments);
        if (!this.mukAiInComposer) {
            return;
        }
        const group = document.createElement('div');
        group.className = 'mk_ai_write btn-group';
        group.innerHTML =
            '<div class="btn editor-ignore"><span class="mk_icon_ai fa-fw"/></div>';
        group.title = _t('Write with AI');
        group.addEventListener('click', this.mukAiOpenPanel);
        wysiwyg.toolbar.el.append(group);
        wysiwyg.odooEditor.editable.addEventListener(OPEN_EVENT, this.mukAiOpenPanel);
    },
    /**
     * Open the writing helper over the cursor, about the record the mail is
     * written on.
     */
    openComposePanel() {
        const { model, res_id: resId } = this.props.record.data;
        const editor = this.wysiwyg.odooEditor;
        const anchor = editor.isSelectionInEditable()
            ? closestBlock(editor.document.getSelection().anchorNode)
            : editor.editable;
        this.mukAiPopover.add(
            anchor,
            ComposePanel,
            {
                adapter: makeEditorAdapter(editor, {
                    resModel: (resId && model) || false,
                    resId: resId || false,
                }),
            },
            {
                position: 'bottom-start',
                popoverClass: 'mk_compose_panel_popover',
                closeOnClickAway: false,
            },
        );
    },
});
