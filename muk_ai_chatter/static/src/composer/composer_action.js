import { _t } from '@web/core/l10n/translation';
import { usePopover } from '@web/core/popover/popover_hook';

import { registerComposerAction } from '@mail/core/common/composer_actions';

import { makeTextComposerAdapter } from '@muk_ai_chatter/composer/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel';

registerComposerAction('muk-ai-write', {
    // Staff only, and stated as such: a guest has no `self_partner` at all,
    // and a merely falsy `share` would offer them a panel they may not use.
    condition: ({ store }) => store.self_partner?.main_user_id?.share === false,
    icon: 'mk_icon_ai',
    name: _t('Write with AI'),
    setup: ({ owner }) => {
        owner.mukAiWritePopover = usePopover(ComposePanel, {
            position: 'top-start',
            popoverClass: 'o-mail-ComposePanel-popover',
            // Clicking away leaves the panel open on purpose: a draft the
            // user is reading is thrown away by the stray click that put the
            // cursor back in the message. Escape and Discard close it.
            closeOnClickAway: false,
        });
    },
    onSelected: ({ composer, owner }) => {
        // Anchored on the composer root, which outlives the re-renders typing
        // causes: a popover whose anchor is replaced under it drifts off to a
        // corner of the screen.
        const anchor = owner.root?.el || owner.inputContainerRef?.el;
        if (!anchor) {
            return;
        }
        owner.mukAiWritePopover.open(anchor, {
            adapter: makeTextComposerAdapter(composer, owner.ref?.el),
            close: () => owner.mukAiWritePopover.close(),
        });
    },
    sequenceQuick: 25,
});
