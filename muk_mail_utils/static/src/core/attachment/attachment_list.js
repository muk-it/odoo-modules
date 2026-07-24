import { patch } from '@web/core/utils/patch';

import { AttachmentList } from '@mail/core/common/attachment_list';

AttachmentList.props = [...AttachmentList.props, 'readonly?'];

/** Suppress the delete action when the list is rendered read-only. */
patch(AttachmentList.prototype, {
    get showDelete() {
        if (this.props.readonly) {
            return false;
        }
        return super.showDelete;
    },
});
