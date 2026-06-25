import { Component } from '@odoo/owl';

import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';

/** Artifacts tab listing the session's attachments as cards. */
export class AttachmentsTab extends Component {
    static template = 'muk_ai.AttachmentsTab';
    static components = { AttachmentCard };
    static props = {
        items: { type: Array },
        session: { type: Object, optional: true },
        onOpenAttachment: { type: Function, optional: true },
    };
    onOpen(attachment) {
        if (this.props.onOpenAttachment) {
            this.props.onOpenAttachment(attachment);
        }
    }
}
