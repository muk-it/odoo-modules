// @odoo-module

/**
 * Open files in a viewer tab.
 *
 * Stands in for ``@web/core/file_viewer/file_viewer_hook``, which Odoo 16 does
 * not have. 16's own viewer lives inside the legacy messaging models and cannot
 * be driven from an unrelated component, so viewable files are opened through
 * their own source URL instead.
 *
 * @returns {{open: (file: object) => void, close: () => void}} viewer API
 */
export function useFileViewer() {
    return {
        open(file) {
            if (!file) {
                return;
            }
            const href = file.defaultSource || file.downloadUrl;
            if (href) {
                window.open(href, '_blank', 'noopener,noreferrer');
            }
        },
        close() {},
    };
}
