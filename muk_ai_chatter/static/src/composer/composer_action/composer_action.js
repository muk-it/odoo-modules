import { _t } from '@web/core/l10n/translation';
import { usePopover } from '@web/core/popover/popover_hook';

import { registerComposerAction } from '@mail/core/common/composer_actions';

import { makeTextComposerAdapter } from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';
import { OPEN_EVENT } from '@muk_ai_chatter/composer/editor_plugin/editor_plugin';

registerComposerAction('muk-ai-write', {
    condition: ({ store }) => store.self_partner?.main_user_id?.share === false,
    icon: 'mk_icon_ai',
    name: _t('Write with AI'),
    setup: ({ owner }) => {
        owner.mukAiWritePopover = usePopover(ComposePanel, {
            position: 'top-start',
            popoverClass: 'mk_compose_panel_popover',
            closeOnClickAway: false,
        });
    },
    onSelected: ({ composer, owner }) => {
        if (owner.editor) {
            owner.editor.editable.dispatchEvent(new CustomEvent(OPEN_EVENT));
            return;
        }
        owner.mukAiWritePopover.open(owner.root.el, {
            adapter: makeTextComposerAdapter(composer, owner.ref.el),
            close: () => owner.mukAiWritePopover.close(),
        });
    },
    sequenceQuick: 25,
});
