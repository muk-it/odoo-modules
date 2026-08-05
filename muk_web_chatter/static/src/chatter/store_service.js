import { patch } from '@web/core/utils/patch';

import { Store } from '@mail/core/common/store_service';

/** Let the server notify the internal followers when posting an internal note. */
patch(Store.prototype, {
    /**
     * Flag the post request so that the internal followers become recipients.
     * @returns {Promise<object>} the message post parameters
     */
    async getMessagePostParams({ postData }) {
        const params = await super.getMessagePostParams(...arguments);
        if (postData?.notifyInternalFollowers) {
            params.context = {
                ...params.context,
                mail_notify_internal_followers: true,
            };
        }
        return params;
    },
});
