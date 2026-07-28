// @odoo-module

import { url } from '@web/core/utils/urls';
import { patch } from '@web/core/utils/patch';
import { archParseBoolean } from '@web/views/utils';
import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';

import { BinaryField, ListBinaryField, listBinaryField } from '@web/views/fields/binary/binary_field';

patch(BinaryField.prototype, {
    setup() {
        super.setup();
        this.fileViewer = useFileViewer();
    },
    get isText() {
        const textExtensions = [
            '.js',
            '.json',
            '.css',
            '.html',
            '.txt',
        ];
        return textExtensions.some(
            ext => this.fileName.toLowerCase().endsWith(ext)
        );
    },
    get isPdf() {
        return this.fileName.endsWith('.pdf');
    },
    get isImage() {
        const imageExtensions = [
            '.bmp',
            '.gif',
            '.jpg',
            '.jpeg',
            '.png',
            '.svg',
            '.tif',
            '.tiff',
            '.ico',
            '.webp'
        ];
        return imageExtensions.some(
            ext => this.fileName.toLowerCase().endsWith(ext)
        );
    },
    get isVideo() {
        const videoExtensions = [
            '.mp3',
            '.mkv',
            '.mp4',
            '.webm',
        ];
        return videoExtensions.some(
            ext => this.fileName.toLowerCase().endsWith(ext)
        );
    },
    get isViewable() {
        return (
            this.isText || 
            this.isImage || 
            this.isVideo || 
            this.isPdf
        );
    },
    get defaultSource() {
        const route = url(this.urlRoute, this.urlQueryParams);
        const encodedRoute = encodeURIComponent(route);
        if (this.isPdf) {
            return `/web/static/lib/pdfjs/web/viewer.html?file=${encodedRoute}#pagemode=none`;
        }
        return route;
    },
    get downloadUrl() {
        return url(this.urlRoute, { ...this.urlQueryParams, download: true });
    },
    get urlQueryParams() {
        return {
            model: this.props.record.resModel,
            id: this.props.record.resId,
            field: this.props.name,
            filename_field: this.fileName,
            filename: this.fileName || '',
        };
    },
    get urlRoute() {
        return (
            this.isImage ? 
            `/web/image/${this.props.record.resId}` : 
            `/web/content/${this.props.record.resId}`
        );
    },
    get fileModel() {
        return {
            isText: this.isText,
            isPdf: this.isPdf,
            isImage: this.isImage,
            isVideo: this.isVideo,
            isViewable: this.isViewable,
            displayName: this.fileName || '',
            defaultSource: this.defaultSource,
            downloadUrl: this.downloadUrl,
        };
    },
    onFilePreview() {
        this.fileViewer.open(this.fileModel);
    }
});

patch(ListBinaryField, {
    props: {
        ...ListBinaryField.props,
        noLabel: { type: Boolean, optional: true },
    },
    defaultProps: {
        ...ListBinaryField.defaultProps,
        noLabel: false,
    },
});

patch(listBinaryField, {
    extractProps({ attrs }) {
        const props = super.extractProps(...arguments);
        props.noLabel = archParseBoolean(attrs.nolabel);
        return props;
    },
});

