import { url } from '@web/core/utils/urls';
import { patch } from '@web/core/utils/patch';

import { FileModel } from '@web/core/file_viewer/file_model';
import { Attachment } from '@mail/core/common/attachment_model';

const TEXT_MIMETYPES = [
    'text/csv',
    'text/markdown',
    'text/xml',
    'text/x-python',
    'text/x-rst',
    'text/x-yaml',
    'application/xml',
    'application/x-yaml',
    'application/x-sh',
    'application/sql',
];

const CSV_MIMETYPES = [
    'text/csv',
    'text/tab-separated-values',
];

const patchModel = {
    get isMail() {
        return this.mimetype && this.mimetype.startsWith('message/rfc822');
    },
    get isCSV() {
        return CSV_MIMETYPES.includes(this.mimetype) || (
            this.name && /\.(csv|tsv)$/i.test(this.name)
        );
    },
    get isText() {
        return super.isText || TEXT_MIMETYPES.includes(this.mimetype);
    },
    get isViewable() {
        return super.isViewable || (!this.uploading && (
            this.isMail || this.isCSV
        ));
    },
    get defaultSource() {
        if (this.isMail) {
            return url(
                `/muk_web_preview/preview/mail/${this.id}`,
                this.urlQueryParams,
            );
        }
        if (this.isCSV) {
            return url(
                `/muk_web_preview/preview/csv/${this.id}`,
                this.urlQueryParams,
            );
        }
        return super.defaultSource;
    },
};

patch(FileModel.prototype, patchModel);
patch(Attachment.prototype, patchModel);
