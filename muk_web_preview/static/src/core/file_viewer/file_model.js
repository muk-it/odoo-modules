import { patch } from '@web/core/utils/patch';
import { url } from '@web/core/utils/urls';
import { session } from '@web/session';

import { FileModel } from '@web/core/file_viewer/file_model';
import { Attachment } from '@mail/core/common/attachment_model';

const RENDERED_TYPES = [
    {
        mimetypes: ['text/csv', 'text/tab-separated-values', 'application/csv'],
        extension: /\.(csv|tsv)$/i,
    },
    { mimetypes: ['message/rfc822'], extension: /\.eml$/i },
    { mimetypes: ['application/vnd.ms-outlook'], extension: /\.msg$/i },
];

const TEXT_MIMETYPES = [
    'application/sql',
    'application/x-sh',
    'application/x-yaml',
    'text/x-python',
    'text/x-rst',
    'text/x-yaml',
];

const OFFICE_MIMETYPES = [
    'application/msword',
    'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
];

/** Tables, email files and source code open in the text preview, Office files online. */
const filePatch = {
    get isRendered() {
        return RENDERED_TYPES.some(
            ({ mimetypes, extension }) =>
                mimetypes.includes(this.mimetype) || extension.test(this.name || ''),
        );
    },
    get isOffice() {
        return (
            Boolean(session.preview_office_enabled) &&
            !this.isRendered &&
            (OFFICE_MIMETYPES.includes(this.mimetype) ||
                /\.(docx?|xlsx?|pptx?)$/i.test(this.name || ''))
        );
    },
    get isText() {
        return (
            super.isText || this.isRendered || TEXT_MIMETYPES.includes(this.mimetype)
        );
    },
    get isViewable() {
        return super.isViewable || (this.isOffice && !this.uploading);
    },
};

patch(Attachment.prototype, filePatch);
patch(FileModel.prototype, filePatch);
patch(FileModel.prototype, {
    get defaultSource() {
        if (this.isRendered && this.id) {
            return url(
                `/mail/attachment/render_text/${encodeURIComponent(this.id)}`,
                this.urlQueryParams,
            );
        }
        return super.defaultSource;
    },
});
