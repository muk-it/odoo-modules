import { browser } from '@web/core/browser/browser';
import { _t } from '@web/core/l10n/translation';
import { download } from '@web/core/network/download';
import { rpc } from '@web/core/network/rpc';
import { registry } from '@web/core/registry';
import { user } from '@web/core/user';
import { patch } from '@web/core/utils/patch';
import { url } from '@web/core/utils/urls';
import { session } from '@web/session';

import { FileModel } from '@web/core/file_viewer/file_model';
import { FileViewer } from '@web/core/file_viewer/file_viewer';
import { downloadReport, getReportUrl } from '@web/webclient/actions/reports/utils';

const PREVIEW_ROUTE = '/web_preview/report';

/** A rendered report, shown inline in the file viewer and downloaded on request. */
class ReportFile extends FileModel {
    /**
     * @param {object} action the report action
     * @param {object} params the `data` and `context` of the report download
     */
    constructor(action, params) {
        super();
        this.name = action.name;
        this.mimetype =
            action.report_type === 'qweb-text' ? 'text/plain' : 'application/pdf';
        this.params = params;
    }
    get urlRoute() {
        return PREVIEW_ROUTE;
    }
    get urlQueryParams() {
        return this.params;
    }
    /**
     * Download the report under the file name the server gives it.
     * @returns {Promise<void>}
     */
    download() {
        return download({ url: '/report/download', data: this.params });
    }
}

/**
 * Return the download parameters of a PDF or text report the server can render.
 * @param {object} action the report action
 * @returns {Promise<object|null>}
 */
async function getReportParams(action) {
    const [, type, engineName] =
        action.report_type.match(/^qweb-(pdf|text)(?:-(.+))?$/) || [];
    if (!type) {
        return null;
    }
    if (type === 'pdf') {
        downloadReport.reportingEngineStatusProm ||= rpc(
            '/report/get_pdf_engine_state',
            engineName ? { engine_name: engineName } : {},
        );
        const status = await downloadReport.reportingEngineStatusProm;
        if (!['ok', 'upgrade'].includes(status)) {
            return null;
        }
    }
    return {
        data: JSON.stringify([getReportUrl(action, type), action.report_type]),
        context: JSON.stringify({ ...user.context, ...action.context }),
    };
}

/**
 * Show a report flagged for the preview in the file viewer.
 * @param {object} action the report action
 * @param {object} options the action options
 * @param {object} env
 * @returns {Promise<boolean>}
 */
async function previewReportHandler(action, options, env) {
    const params = action.preview && (await getReportParams(action));
    if (!params) {
        return false;
    }
    env.services.fileViewer().open(new ReportFile(action, params));
    return true;
}

/**
 * Open a downloaded report in a new tab as well when the settings ask for it,
 * except on a small screen.
 * @param {object} action the report action
 * @param {object} options the action options
 * @param {object} env
 * @returns {Promise<boolean>}
 */
async function openReportHandler(action, options, env) {
    const params =
        session.preview_report_open &&
        !env.services.ui.isSmall &&
        (await getReportParams(action));
    if (params && !browser.open(url(PREVIEW_ROUTE, params), '_blank')) {
        env.services.notification.add(
            _t('The browser blocked the report tab. Allow pop-ups for this site.'),
            { type: 'warning' },
        );
    }
    return false;
}

/** The download button of the file viewer downloads a report through its POST route. */
patch(FileViewer.prototype, {
    onClickDownload() {
        if (this.state.file instanceof ReportFile) {
            return this.state.file.download();
        }
        return super.onClickDownload();
    },
});

registry
    .category('ir.actions.report handlers')
    .add('muk_web_preview.preview', previewReportHandler, { sequence: 1 })
    .add('muk_web_preview.open', openReportHandler, { sequence: 100 });
