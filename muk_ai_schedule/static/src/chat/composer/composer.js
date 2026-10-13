// @odoo-module

import { _t } from '@muk_ai/core/compat/translation';
import { patch } from '@web/core/utils/patch';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { WaitBar, wakeupPlan } from '@muk_ai_schedule/chat/wait_bar/wait_bar';

ChatComposer.components = { ...ChatComposer.components, WaitBar };

patch(ChatComposer.prototype, 'muk_ai_schedule.composer', {
    get composerPlaceholder() {
        return this.props.session && wakeupPlan(this.props.session.state)
            ? _t('Waiting. Type to wake the agent...')
            : this.props.placeholder;
    },
});
