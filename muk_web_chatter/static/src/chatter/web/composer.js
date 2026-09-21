import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';
import { Composer } from '@mail/core/common/composer';

import '@mail/chatter/web/composer_patch';

/** Tailor the send label, placeholder, and post target for internal-follower notes. */
patch(Composer.prototype, {
    get isInternalNote() {
        return (
            this.props.type === 'note' &&
            Boolean(this.env.inChatter?.notifyInternalFollowers)
        );
    },
    get SEND_TEXT() {
        if (this.isInternalNote) {
            return _t('Send');
        }
        return super.SEND_TEXT;
    },
    get placeholder() {
        if (this.isInternalNote) {
            return _t('Send a message to internal followers...');
        }
        return super.placeholder;
    },
    get postData() {
        const postData = super.postData;
        postData.notifyInternalFollowers = this.isInternalNote;
        return postData;
    },
    get fullComposerAdditionalContext() {
        const context = super.fullComposerAdditionalContext;
        if (this.isInternalNote) {
            context.mail_notify_internal_followers = true;
        }
        return context;
    },
});
