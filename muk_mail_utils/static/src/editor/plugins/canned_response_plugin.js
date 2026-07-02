import { _t } from '@web/core/l10n/translation';

import { Plugin } from '@html_editor/plugin';
import { MAIN_PLUGINS } from '@html_editor/plugin_sets';
import { isHtmlContentSupported } from '@html_editor/core/selection_plugin';

import { CannedResponseDialog } from '@muk_mail_utils/editor/plugins/canned_response_dialog';

/**
 * Adds a powerbox command to insert mail canned responses into any html
 * editor field. Odoo only offers canned responses (via "::") in the Discuss
 * and chatter composers, so this closes the gap for the full composer and
 * regular html fields.
 */
export class CannedResponsePlugin extends Plugin {
    static id = 'mukCannedResponse';
    static dependencies = ['history', 'dom', 'selection', 'dialog'];
    resources = {
        user_commands: [
            {
                id: 'mukInsertCannedResponse',
                title: _t('Canned Response'),
                description: _t('Insert a canned response'),
                icon: 'fa-file-text-o',
                run: this.openCannedResponseDialog.bind(this),
                isAvailable: isHtmlContentSupported,
            },
        ],
        powerbox_items: [
            {
                categoryId: 'widget',
                commandId: 'mukInsertCannedResponse',
                keywords: ['canned', 'response', 'snippet', 'template'],
            },
        ],
    };

    /** Opens the search dialog and inserts the selected substitution text. */
    openCannedResponseDialog() {
        const cursors = this.dependencies.selection.preserveSelection();
        this.services.dialog.add(
            CannedResponseDialog,
            {
                search: (searchValue) =>
                    this.services.orm.searchRead(
                        'mail.canned.response',
                        searchValue
                            ? [
                                  '|',
                                  ['source', 'ilike', searchValue],
                                  ['substitution', 'ilike', searchValue],
                              ]
                            : [],
                        ['source', 'substitution'],
                        { limit: 50, order: 'source asc' },
                    ),
                select: (cannedResponse) => {
                    cursors.restore();
                    this.dependencies.dom.insert(
                        this.buildSubstitutionFragment(cannedResponse.substitution),
                    );
                    this.dependencies.history.addStep();
                },
            },
            { onClose: () => this.dependencies.selection.focusEditable() },
        );
    }

    /**
     * Builds an insertable fragment from the substitution text, converting
     * line breaks to `<br>` elements.
     * @param {string} substitution
     * @returns {DocumentFragment}
     */
    buildSubstitutionFragment(substitution) {
        const fragment = this.document.createDocumentFragment();
        substitution.split(/\r?\n/).forEach((line, index) => {
            if (index > 0) {
                fragment.appendChild(this.document.createElement('br'));
            }
            fragment.appendChild(this.document.createTextNode(line));
        });
        return fragment;
    }
}

MAIN_PLUGINS.push(CannedResponsePlugin);
