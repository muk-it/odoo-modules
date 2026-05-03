import base64

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import ids_field


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_report(self, report_ref):
        if isinstance(report_ref, int):
            return self.env['ir.actions.report'].browse(
                report_ref
            )
        if '.' in (ref := (report_ref or '').strip()):
            report = self.env.ref(ref, raise_if_not_found=False)
            if report and report._name == 'ir.actions.report':
                return report
        return self.env['ir.actions.report'].search(
            [('report_name', '=', ref)], limit=1,
        )

    @api.model
    def _report_mimetype(self, report_type):
        if report_type == 'pdf':
            return 'application/pdf', 'pdf'
        if report_type == 'text':
            return 'text/plain', 'txt'
        if report_type == 'html':
            return 'text/html', 'html'
        return 'application/octet-stream', report_type

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='print_report',
        description=(
            "Render an Odoo report for one or more records and return the "
            "binary as base64. Accepts a report xmlid (e.g. "
            "'sale.action_report_saleorder'), a report_name "
            "(e.g. 'sale.report_saleorder'), or the numeric id of an "
            "ir.actions.report."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'report_ref': {
                    'type': ['string', 'integer'],
                    'description': (
                        "Report xmlid, report_name, or id of the "
                        "ir.actions.report to render."
                    ),
                },
                'ids': ids_field('render'),
            },
            'required': ['report_ref', 'ids'],
        },
        category='read',
    )
    def _mcp_print_report(self, report_ref, ids):
        if not (target_ids := self._normalize_ids(ids)):
            raise UserError(_('No record IDs provided'))
        if not (report := self._resolve_report(report_ref)):
            raise UserError(_("Report %r not found.", report_ref))
        content, report_type = report._render(report.report_name, target_ids)
        mimetype, extension = self._report_mimetype(report_type)
        name = report.name or report.report_name or 'report'
        if isinstance(content, str):
            content = content.encode()
        return {
            'filename': '%s.%s' % (name.replace(' ', '_'), extension),
            'mimetype': mimetype,
            'content_base64': base64.b64encode(content).decode(),
        }
