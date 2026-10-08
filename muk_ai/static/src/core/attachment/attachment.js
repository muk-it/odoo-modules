import { Component, t, useProps } from '@odoo/owl';

import { FileModel } from '@web/core/file_viewer/file_model';
import { humanSize } from '@web/core/utils/binary';

const EXTENSION_MIMETYPES = {
    md: 'text/markdown',
    markdown: 'text/markdown',
    txt: 'text/plain',
    csv: 'text/csv',
};

/** A file shown from a data or image URL rather than from an attachment. */
class InlineImageFile extends FileModel {
    get defaultSource() {
        return this.url;
    }
    get downloadUrl() {
        return this.url;
    }
}

/**
 * Wrap an attachment descriptor in a file-viewer model.
 * @param {object} descriptor `{id, filename, mimetype, size}`
 * @returns {FileModel} the file model
 */
export function toFileModel({ id, filename, mimetype }) {
    return Object.assign(new FileModel(), {
        id,
        name: filename,
        mimetype,
        type: 'binary',
    });
}

/**
 * Build a file-viewer model for an image shown inline in a message.
 * @param {string} src the image URL
 * @returns {FileModel} the file model
 */
export function toInlineImageFile(src) {
    return Object.assign(new InlineImageFile(), {
        id: -1,
        name: 'image.png',
        mimetype: 'image/png',
        type: 'binary',
        url: src,
    });
}

/**
 * Read a browser file into the payload `upload_attachments` takes.
 * @param {File} file the file to read
 * @returns {Promise<object>} `{filename, mimetype, data_b64}`
 */
export function fileToBase64(file) {
    const extension = file.name.includes('.') ? file.name.split('.').pop() : '';
    const mimetype = file.type || EXTENSION_MIMETYPES[extension.toLowerCase()] || '';
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result || '';
            resolve({
                filename: file.name,
                mimetype,
                data_b64: result.slice(result.indexOf(',') + 1),
            });
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

/**
 * Collect the files of a paste or drop event.
 * @param {DataTransfer|null} transfer the event's clipboard or drag data
 * @returns {File[]} the files it carries
 */
export function transferFiles(transfer) {
    return [...(transfer?.items || [])]
        .filter((item) => item.kind === 'file')
        .map((item) => item.getAsFile())
        .filter(Boolean);
}

/** Card previewing one attachment with its name, size or thumbnail. */
export class AttachmentCard extends Component {
    static template = 'muk_ai.AttachmentCard';
    props = useProps({
        attachment: t.object(),
        removable: t.boolean().optional(false),
        compact: t.boolean().optional(false),
        onOpen: t.function().optional(),
        onRemove: t.function().optional(),
    });
    get file() {
        return toFileModel(this.props.attachment);
    }
    get size() {
        const { size, file_size } = this.props.attachment;
        return size || file_size ? humanSize(size || file_size) : '';
    }
}
