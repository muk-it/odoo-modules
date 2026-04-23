/** @odoo-module */

import { FileModelMixin } from '@web/core/file_viewer/file_model';

const EXTRA_TEXT_MIMETYPES = ['text/csv', 'text/markdown'];

class AIAttachment extends FileModelMixin(Object) {
    constructor({ id, filename, mimetype, size }) {
        super();
        this.id = id;
        this.name = filename;
        this.mimetype = mimetype;
        this.size = size;
        this.type = 'binary';
    }

    get isText() {
        return super.isText || EXTRA_TEXT_MIMETYPES.includes(this.mimetype);
    }
}

export function toFileModel(descriptor) {
    return descriptor instanceof AIAttachment ? descriptor : new AIAttachment(descriptor);
}

export function toFileModels(descriptors) {
    return (descriptors || []).map(toFileModel);
}
