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

class InlineImageFile extends FileModelMixin(Object) {
    constructor(dataUrl, { name = 'generated.png', mimetype = 'image/png' } = {}) {
        super();
        this._src = dataUrl;
        this.id = -1;
        this.name = name;
        this.mimetype = mimetype;
        this.type = 'binary';
    }
    get defaultSource() {
        return this._src;
    }
    get downloadUrl() {
        return this._src;
    }
}

export function toFileModel(descriptor) {
    return descriptor instanceof AIAttachment ? descriptor : new AIAttachment(descriptor);
}

export function toFileModels(descriptors) {
    return (descriptors || []).map(toFileModel);
}

export function toInlineImageFile(src, options) {
    return new InlineImageFile(src, options);
}
