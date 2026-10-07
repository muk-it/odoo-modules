from __future__ import annotations

from odoo.http import Response, route

from odoo.addons.web.controllers import report


class ReportController(report.ReportController):
    """Show rendered reports in the browser instead of downloading them."""

    # ----------------------------------------------------------
    # Routes
    # ----------------------------------------------------------

    @route('/web_preview/report', type='http', auth='user')
    def report_preview(self, data: str, context: str | None = None) -> Response:
        """Render a report like its download and serve it inline."""
        response = self.report_download(data, context)
        response.headers['Content-Disposition'] = response.headers[
            'Content-Disposition'
        ].replace('attachment', 'inline', 1)
        return response
