import { patch } from '@web/core/utils/patch';

import { Attachment } from '@mail/core/common/attachment_model';

/** Suppress the delete action on attachments flagged as non-deletable. */
patch(Attachment.prototype, {
    get isDeletable() {
        if (this.disableDeletable) {
            return false;
        }
        return super.isDeletable;
    },
});
