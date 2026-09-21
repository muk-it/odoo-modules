import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import { RecipientsInput } from '@mail/core/web/recipients_input';

/** Summarise the internal followers while an internal note is being written. */
patch(RecipientsInput.prototype, {
    get isInternalNote() {
        return Boolean(this.env.inChatter?.notifyInternalFollowers);
    },
    get internalFollowers() {
        return [...this.props.thread.followers].filter(
            (follower) =>
                follower.partner_id?.main_user_id &&
                follower.partner_id.main_user_id.share === false,
        );
    },
    get showFollowersBadge() {
        if (this.props.recipientType !== 'to') {
            return false;
        }
        if (this.isInternalNote) {
            return this.internalFollowers.length > 0;
        }
        return this.props.thread.recipientsCount > 0;
    },
    /** Keep the suggested recipients out of an internal note. */
    getAllMailThreadRecipients() {
        const recipients = super.getAllMailThreadRecipients();
        if (!this.isInternalNote) {
            return recipients;
        }
        const suggested = new Set(this.props.thread.suggestedRecipients);
        return recipients.filter((recipient) => !suggested.has(recipient));
    },
    getTagsFromMailThread() {
        const tags = super.getTagsFromMailThread();
        if (!this.isInternalNote) {
            return tags;
        }
        const suggested = new Set(
            this.props.thread.suggestedRecipients.map(
                (recipient) => recipient.partner_id,
            ),
        );
        return tags.filter((tag) => !suggested.has(tag.resId));
    },
    getPlaceholder() {
        if (this.isInternalNote && this.props.recipientType === 'to') {
            return this.getAllMailThreadRecipients().length
                ? ''
                : _t('Internal followers only');
        }
        return super.getPlaceholder();
    },
    get followersBadge() {
        if (!this.isInternalNote) {
            return super.followersBadge;
        }
        const followers = this.internalFollowers;
        const text =
            followers.length === 1
                ? _t('1 Internal Follower')
                : _t('%(followersCount)s Internal Followers', {
                      followersCount: followers.length,
                  });
        return {
            color: 4,
            text,
            tooltip: followers
                .map((follower) => {
                    const name =
                        this.props.thread.getPersonaName(follower.partner_id) ||
                        _t('Unnamed');
                    const email = follower.partner_id.email;
                    return email ? `${name} <${email}>` : name;
                })
                .join('\n'),
        };
    },
});
