import { Component } from '@odoo/owl';

import { humanSize } from '@web/core/utils/binary';

import { toFileModel } from '@muk_ai/core/attachment/attachment';

/** Compact card previewing a single attachment with name, size, and thumbnail. */
export class AttachmentCard extends Component {
    static template = 'muk_ai.AttachmentCard';
    static props = {
        attachment: { type: Object },
        removable: { type: Boolean, optional: true },
        compact: { type: Boolean, optional: true },
        onOpen: { type: Function, optional: true },
        onRemove: { type: Function, optional: true },
    };
    static defaultProps = {
        removable: false,
        compact: false,
    };
    get file() {
        return toFileModel(this.props.attachment);
    }
    get humanSize() {
        const size = this.props.attachment.size || this.props.attachment.file_size;
        return size ? humanSize(size) : '';
    }
    onClick() {
        if (this.props.onOpen) {
            this.props.onOpen(this.props.attachment);
        }
    }
    onRemove(event) {
        event.stopPropagation();
        if (this.props.onRemove) {
            this.props.onRemove(this.props.attachment);
        }
    }
}
