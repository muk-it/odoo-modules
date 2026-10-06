import { useEffect } from '@odoo/owl';
import { rpc } from '@web/core/network/rpc';
import { patch } from '@web/core/utils/patch';

import { FileViewer } from '@web/core/file_viewer/file_viewer';

/** Load the Office Online viewer URL whenever an Office file becomes active. */
patch(FileViewer.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.officeUrl = null;
        this.state.officeFailed = false;
        useEffect(() => {
            const file = this.state.file;
            this.state.officeUrl = null;
            this.state.officeFailed = false;
            if (file.isOffice) {
                this.loadOfficeUrl(file);
            }
        });
    },
    /**
     * Fetch the viewer URL of a file, dropping the answer once another file is active.
     * @param {object} file
     * @returns {Promise<void>}
     */
    async loadOfficeUrl(file) {
        try {
            const officeUrl = await rpc(`/web_preview/office/${file.id}`);
            if (this.state.file === file) {
                this.state.officeUrl = officeUrl;
            }
        } catch {
            if (this.state.file === file) {
                this.state.officeFailed = true;
            }
        }
    },
});
