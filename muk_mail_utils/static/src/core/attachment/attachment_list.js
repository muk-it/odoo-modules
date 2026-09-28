import { AttachmentList } from '@mail/core/common/attachment_list';

/** Attachment list without the delete action, for read-only previews. */
export class ReadonlyAttachmentList extends AttachmentList {
    showDelete() {
        return false;
    }
}
