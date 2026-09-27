import { patch } from '@web/core/utils/patch';
import { Store } from '@mail/core/common/store_service';

/** Let an internal note reach the internal followers and the tagged recipients. */
patch(Store.prototype, {
    async getMessagePostParams({ postData, thread }) {
        const params = await super.getMessagePostParams(...arguments);
        if (!postData.notifyInternalFollowers) {
            return params;
        }
        for (const recipient of thread.additionalRecipients) {
            const cc = recipient.recipient_type === 'cc' ? 'cc_' : '';
            const field = recipient.partner_id ? 'ids' : 'emails';
            (params.post_data[`partner_${cc}${field}`] ??= []).push(
                recipient.partner_id || recipient.email,
            );
        }
        params.context = {
            ...params.context,
            mail_notify_internal_followers: true,
        };
        return params;
    },
});
