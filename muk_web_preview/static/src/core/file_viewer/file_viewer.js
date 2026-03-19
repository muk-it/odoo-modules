import { patch } from '@web/core/utils/patch';
import { rpc } from '@web/core/network/rpc';

import { FileViewer } from '@web/core/file_viewer/file_viewer';

patch(FileViewer.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.officeSource = null;
        this.state.officeLoading = false;
        this._loadOfficePreview();
    },
    activateFile(index) {
        super.activateFile(index);
        this.state.officeSource = null;
        this.state.officeLoading = false;
        this._loadOfficePreview();
    },
    async _loadOfficePreview() {
        const file = this.state.file;
        if (!file.isOffice) {
            return;
        }
        this.state.officeLoading = true;
        try {
            const result = await rpc(
                '/muk_web_preview/office/token',
                { attachment_id: file.id },
            );
            if (this.state.file === file) {
                this.state.officeSource = result.viewer_url;
                this.state.officeLoading = false;
            }
        } catch {
            this.state.officeLoading = false;
            this.state.officeSource = null;
        }
    },
});
