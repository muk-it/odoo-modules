// @odoo-module

import { url } from '@web/core/utils/urls';

const IMAGE_MIMETYPES = [
    'image/bmp',
    'image/gif',
    'image/jpeg',
    'image/png',
    'image/svg+xml',
    'image/tiff',
    'image/x-icon',
    'image/webp',
];

const TEXT_MIMETYPES = [
    'application/javascript',
    'application/json',
    'text/css',
    'text/html',
    'text/plain',
];

/**
 * File-model mixin mirroring the ``@web/core/file_viewer/file_model`` API.
 *
 * Odoo 16 has no core file viewer, so the subset the chat surfaces rely on
 * (viewability checks, source and download URLs) is provided here.
 *
 * @param {Function} T base class to extend
 * @returns {Function} the extended class
 */
export const FileModelMixin = (T) =>
    class extends T {
        get defaultSource() {
            const route = url(this.urlRoute, this.urlQueryParams);
            if (this.isPdf) {
                const encoded = encodeURIComponent(route);
                return `/web/static/lib/pdfjs/web/viewer.html?file=${encoded}#pagemode=none`;
            }
            return route;
        }

        get displayName() {
            return this.name || this.filename;
        }

        get downloadUrl() {
            return url(this.urlRoute, { ...this.urlQueryParams, download: true });
        }

        get isImage() {
            return IMAGE_MIMETYPES.includes(this.mimetype);
        }

        get isPdf() {
            return !!this.mimetype && this.mimetype.startsWith('application/pdf');
        }

        get isText() {
            return TEXT_MIMETYPES.includes(this.mimetype);
        }

        get isVideo() {
            return !!this.mimetype && this.mimetype.startsWith('video');
        }

        get isViewable() {
            return (
                (this.isText || this.isImage || this.isVideo || this.isPdf) &&
                !this.uploading
            );
        }

        get urlQueryParams() {
            return this.access_token ? { access_token: this.access_token } : {};
        }

        get urlRoute() {
            return this.isImage ? `/web/image/${this.id}` : `/web/content/${this.id}`;
        }
    };
