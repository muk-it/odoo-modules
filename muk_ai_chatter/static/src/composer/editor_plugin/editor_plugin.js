import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import { Plugin } from '@html_editor/plugin';
import { withSequence } from '@html_editor/utils/resource';
import { MAIL_CORE_PLUGINS, MAIL_PLUGINS } from '@mail/core/common/plugin/plugin_sets';
import { HtmlComposerMessageField } from '@mail/views/web/fields/html_composer_message_field/html_composer_message_field';

import { makeEditorAdapter } from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';

export const OPEN_EVENT = 'muk-ai-compose-open';

/**
 * Offer the writing helper in the mail editors: a toolbar button of its own
 * group, a `/` command, and the open event the full composer's button fires.
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
                namespaces: ['compact', 'expanded'],
                description: _t('Write with AI'),
            },
        ],
        powerbox_categories: [withSequence(55, { id: 'muk_ai', name: _t('AI') })],
        powerbox_items: [{ categoryId: 'muk_ai', commandId: 'mukAiWrite' }],
    };
    setup() {
        this.panel = this.dependencies.overlay.createOverlay(ComposePanel, {
            positionOptions: { position: 'bottom-start' },
            closeOnPointerdown: false,
        });
        this.addDomListener(this.editable, OPEN_EVENT, () => this.openPanel());
    }
    openPanel() {
        this.panel.open({
            props: {
                adapter: makeEditorAdapter(this, this.recordOfEditable()),
                close: () => this.panel.close(),
            },
        });
    }
    /**
     * Return the record the mail is written about: the thread when there is
     * one, never the `mail.compose.message` wizard holding the editor.
     * @returns {{resModel: string|false, resId: number|false}} the record
     */
    recordOfEditable() {
        const thread = this.config.thread;
        if (thread?.model && thread?.id) {
            return { resModel: thread.model, resId: thread.id };
        }
        const info = this.config.getRecordInfo?.() || {};
        if (!info.resModel || info.resModel === 'mail.compose.message') {
            return { resModel: false, resId: false };
        }
        return { resModel: info.resModel, resId: info.resId || false };
    }
}

for (const plugins of [MAIL_CORE_PLUGINS, MAIL_PLUGINS]) {
    if (!plugins.includes(ComposeAIPlugin)) {
        plugins.push(ComposeAIPlugin);
    }
}

patch(HtmlComposerMessageField.prototype, {
    getConfig() {
        const config = super.getConfig(...arguments);
        if (!config.Plugins.includes(ComposeAIPlugin)) {
            config.Plugins = [...config.Plugins, ComposeAIPlugin];
        }
        return config;
    },
});
