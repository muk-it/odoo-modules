/** @odoo-module */

import { usePopover } from '@web/core/popover/popover_hook';
import { patch } from '@web/core/utils/patch';

import { Composer } from '@mail/components/composer/composer';

import { makeTextComposerAdapter } from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';

patch(Composer.prototype, 'muk_ai_chatter', {
    setup() {
        this._super(...arguments);
        this.mukAiPopover = usePopover();
    },
    onClickWriteWithAI() {
        const { composer, textareaRef } = this.composerView;
        this.mukAiPopover.add(
            this.root.el,
            ComposePanel,
            { adapter: makeTextComposerAdapter(composer, textareaRef.el) },
            {
                position: 'top-start',
                popoverClass: 'mk_compose_panel_popover',
                closeOnClickAway: false,
            },
        );
    },
});
