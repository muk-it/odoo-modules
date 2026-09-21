import { patch } from '@web/core/utils/patch';
import { Thread } from '@mail/core/common/thread';

const NOTIFICATION_MESSAGE_TYPES = ['user_notification', 'notification'];

/** Optionally hide notification messages from the displayed thread. */
patch(Thread.prototype, {
    get orderedMessages() {
        const messages = super.orderedMessages;
        if (this.env.inChatter?.showNotificationMessages ?? true) {
            return messages;
        }
        return messages.filter(
            (message) => !NOTIFICATION_MESSAGE_TYPES.includes(message.message_type),
        );
    },
});
