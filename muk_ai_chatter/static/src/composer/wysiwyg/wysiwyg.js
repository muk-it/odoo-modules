/** @odoo-module */

import { _t } from '@web/core/l10n/translation';
import { usePopover } from '@web/core/popover/popover_hook';
import { patch } from '@web/core/utils/patch';
import { closestBlock } from '@web_editor/js/editor/odoo-editor/src/utils/utils';
import { Wysiwyg } from '@web_editor/js/wysiwyg/wysiwyg';

import { makeEditorAdapter } from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';
import { OPEN_EVENT } from '@muk_ai_chatter/composer/composer_field/composer_field';

/**
 * Offer the writing helper in the editor of the full mail composer: a toolbar
 * button, a `/` command, and the open event the composer's footer button fires.
 */
patch(Wysiwyg.prototype, {
    setup() {
        super.setup();
        if (this.inDiscuss) {
            this.mukAiPanel = usePopover(ComposePanel, {
                position: 'bottom-start',
                popoverClass: 'mk_compose_panel_popover',
                closeOnClickAway: false,
            });
            this.mukAiOpenPanel = () => this.openComposePanel();
        }
    },
    async startEdition() {
        const result = await super.startEdition(...arguments);
        if (this.inDiscuss) {
            this.odooEditor.editable.addEventListener(OPEN_EVENT, this.mukAiOpenPanel);
        }
        return result;
    },
    destroy() {
        if (this.inDiscuss) {
            this.odooEditor?.editable.removeEventListener(
                OPEN_EVENT,
                this.mukAiOpenPanel,
            );
        }
        super.destroy();
    },
    _getPowerboxOptions() {
        const options = super._getPowerboxOptions();
        if (this.inDiscuss) {
            options.commands.push({
                category: _t('AI Tools'),
                name: _t('Write with AI'),
                description: _t('Rewrite the selection, or write from the record'),
                fontawesome: 'fa-magic',
                priority: 2,
                callback: () => this.openComposePanel(),
            });
        }
        return options;
    },
    _configureToolbar(options) {
        super._configureToolbar(options);
        const button = this.toolbarEl.querySelector('#mk-ai-write');
        if (this.inDiscuss) {
            button?.classList.remove('d-none');
            button?.addEventListener('click', this.mukAiOpenPanel);
        } else {
            button?.remove();
        }
    },
    /**
     * Open the writing helper over the cursor, about the record the mail is
     * written on.
     */
    openComposePanel() {
        const { model, res_ids } = this.props.options.record.data;
        const resId = JSON.parse(res_ids || '[]')[0] || false;
        const editor = this.odooEditor;
        const anchor = editor.isSelectionInEditable()
            ? closestBlock(editor.document.getSelection().anchorNode)
            : editor.editable;
        this.mukAiPanel.open(anchor, {
            adapter: makeEditorAdapter(editor, {
                resModel: (resId && model) || false,
                resId,
            }),
            close: () => this.mukAiPanel.close(),
        });
    },
});
