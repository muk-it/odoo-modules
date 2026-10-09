import { usePopover } from '@web/core/popover/popover_hook';
import { patch } from '@web/core/utils/patch';

import { Composer } from '@mail/core/common/composer';

import { makeTextComposerAdapter } from '@muk_ai_chatter/composer/adapters/adapters';
import { ComposePanel } from '@muk_ai_chatter/composer/compose_panel/compose_panel';

patch(Composer.prototype, {
    setup() {
        super.setup(...arguments);
        this.mukAiWritePopover = usePopover(ComposePanel, {
            position: 'top-start',
            popoverClass: 'mk_compose_panel_popover',
            closeOnClickAway: false,
        });
    },
    onClickWriteWithAI() {
        this.mukAiWritePopover.open(this.root.el, {
            adapter: makeTextComposerAdapter(this.props.composer, this.ref.el),
            close: () => this.mukAiWritePopover.close(),
        });
    },
});
