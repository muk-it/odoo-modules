import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import { withSequence } from '@html_editor/utils/resource';

import { Plugin } from '@html_editor/plugin';
import { MAIL_CORE_PLUGINS, MAIL_PLUGINS } from '@mail/core/common/plugin/plugin_sets';
import { HtmlComposerMessageField } from '@mail/views/web/fields/html_composer_message_field/html_composer_message_field';

import { makeEditorAdapter } from '@muk_ai_chatter/composer/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel';

// Fired on an editable to open the helper over it, so a button outside the
// editor — the one in the full composer's footer — opens the same panel the
// toolbar does, with the same cursor and the same selection.
export const OPEN_EVENT = 'muk-ai-compose-open';

/**
 * Offer the writing helper inside every rich-text editor Odoo mounts.
 *
 * The helper carries its own toolbar group rather than joining an existing
 * one: the group the editor used to keep its AI commands in is being removed
 * upstream, and a button that lands in whichever group happens to exist would
 * move around under us.
 */
export class ComposeAIPlugin extends Plugin {
    static id = 'mukAiCompose';
    static dependencies = ['overlay', 'selection', 'dom', 'history'];

    resources = {
        user_commands: [
            {
                id: 'mukAiWrite',
                title: _t('Write with AI'),
                description: _t('Rewrite the selection, or write from the record'),
                icon: 'mk_icon_ai',
                run: () => this.openPanel(),
            },
        ],
        toolbar_groups: [withSequence(55, { id: 'muk_ai' })],
        toolbar_items: [
            {
                id: 'mukAiWrite',
                groupId: 'muk_ai',
                commandId: 'mukAiWrite',
                description: _t('Write with AI'),
            },
        ],
        powerbox_categories: [withSequence(55, { id: 'muk_ai', name: _t('AI') })],
        powerbox_items: [
            {
                categoryId: 'muk_ai',
                commandId: 'mukAiWrite',
            },
        ],
    };

    setup() {
        this.panel = this.dependencies.overlay.createOverlay(ComposePanel, {
            positionOptions: { position: 'bottom-start' },
        });
        this.addDomListener(this.editable, OPEN_EVENT, () => this.openPanel());
    }
    /**
     * Open the helper over the editable, bound to what is selected right now.
     */
    openPanel() {
        this.panel.open({
            props: {
                adapter: makeEditorAdapter(this, this.recordOfEditable()),
                close: () => this.panel.close(),
            },
        });
    }
    /**
     * Return the record this editable writes about, when it has one.
     *
     * The thread wins where there is one: in the full composer the editable
     * belongs to the `mail.compose.message` wizard, and asking the field which
     * record it edits answers with that wizard rather than with the customer
     * the mail is going to. A composer opened on nothing has no record to
     * name either — the wizard is not one, and handing it over would tell the
     * agent it is writing about a mail it is writing.
     *
     * @returns {{resModel: string|false, resId: number|false}} the record
     */
    recordOfEditable() {
        const thread = this.config.thread;
        if (thread?.model && thread?.id) {
            return { resModel: thread.model, resId: thread.id };
        }
        const config = this.config.getRecordInfo?.() || {};
        if (!config.resModel || config.resModel === 'mail.compose.message') {
            return { resModel: false, resId: false };
        }
        return { resModel: config.resModel, resId: config.resId || false };
    }
}

// Only the mail composers: a writing helper that knows about a thread has
// nothing to say in an arbitrary html field, and the editor of a record or a
// website page belongs to muk_ai_editor. These two sets are the inline
// composer of a chatter and of a conversation.
for (const plugins of [MAIL_CORE_PLUGINS, MAIL_PLUGINS]) {
    if (!plugins.includes(ComposeAIPlugin)) {
        plugins.push(ComposeAIPlugin);
    }
}

// The full composer is the third one, and it is not built from those sets: it
// is an html field, and takes the editor's own plugins. It is offered the
// helper here rather than through MAIN_PLUGINS, which every html field in Odoo
// would inherit — a long mail is exactly what somebody opens it to write.
patch(HtmlComposerMessageField.prototype, {
    getConfig() {
        const config = super.getConfig(...arguments);
        if (!config.Plugins.includes(ComposeAIPlugin)) {
            config.Plugins = [...config.Plugins, ComposeAIPlugin];
        }
        return config;
    },
});
