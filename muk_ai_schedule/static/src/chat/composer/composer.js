import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import { ChatComposer } from '@muk_ai/chat/composer/composer';

patch(ChatComposer.prototype, {
    get placeholder() {
        const data = this.props.session.data;
        return data.state === 'waiting' && data.pending_ask?.kind === 'wakeup'
            ? _t('Waiting. Type to wake the agent...')
            : super.placeholder;
    },
});
