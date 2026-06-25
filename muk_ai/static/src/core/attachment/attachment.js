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

/**
 * Wrap an attachment descriptor in a file-viewer model.
 * @param {object} descriptor attachment descriptor or existing model
 * @returns {AIAttachment} file model
 */
export function toFileModel(descriptor) {
    return descriptor instanceof AIAttachment
        ? descriptor
        : new AIAttachment(descriptor);
}

/**
 * Wrap a list of attachment descriptors in file-viewer models.
 * @param {Array} descriptors attachment descriptors
 * @returns {Array<AIAttachment>} file models
 */
export function toFileModels(descriptors) {
    return (descriptors || []).map(toFileModel);
}

/**
 * Build a file-viewer model for an inline (data-URL) generated image.
 * @param {string} src image data URL
 * @param {object} options optional name and mimetype overrides
 * @returns {InlineImageFile} file model
 */
export function toInlineImageFile(src, options) {
    return new InlineImageFile(src, options);
}
