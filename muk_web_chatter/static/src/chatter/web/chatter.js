import { patch } from '@web/core/utils/patch';
import { browser } from '@web/core/browser/browser';
import { Chatter } from '@mail/chatter/web_portal_project/chatter';

import '@mail/chatter/web/chatter_patch';

/** Restore the notification-message toggle from local storage and persist it. */
patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        Object.assign(this.state, {
            notifyInternalFollowers: false,
            showNotificationMessages:
                browser.localStorage.getItem('muk_web_chatter.notifications') !==
                'false',
        });
    },
    onClickNotificationsToggle() {
        const showNotificationMessages = !this.state.showNotificationMessages;
        browser.localStorage.setItem(
            'muk_web_chatter.notifications',
            showNotificationMessages,
        );
        this.state.showNotificationMessages = showNotificationMessages;
    },
});
