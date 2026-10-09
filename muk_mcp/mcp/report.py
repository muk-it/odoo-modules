import re

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import delivery_field


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_report(self, report_ref):
        ref = str(report_ref).strip()
        if ref.isdigit():
            return self.env['ir.actions.report'].browse(int(ref)).exists()
        if '.' in ref:
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
            "Render an Odoo report for one or more records. Accepts a report "
            "xmlid (e.g. "
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
                'ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Record IDs to render.',
                },
                'delivery': delivery_field(),
            },
            'required': ['report_ref', 'ids'],
        },
        category='read',
    )
    def _mcp_print_report(self, report_ref, ids, delivery='inline'):
        """Render the referenced report for ``ids`` and return the file.

        :raise UserError: when ``ids`` is empty or the report cannot be resolved.
        """
        if not (target_ids := self._normalize_ids(ids)):
            raise UserError(_('No record IDs provided'))
        if not (report := self._resolve_report(report_ref)):
            raise UserError(_("Report %r not found.", report_ref))
        content, report_type = report._render(target_ids)
        mimetype, extension = self._report_mimetype(report_type)
        name = report.name or report.report_name or 'report'
        if report.print_report_name and len(target_ids) == 1:
            name = safe_eval(report.print_report_name, {
                'object': self.env[report.model].browse(target_ids),
                'time': time,
            })
        if isinstance(content, str):
            content = content.encode()
        filename = '%s.%s' % (re.sub(r'[\s/\\]+', '_', name), extension)
        return self._mcp_file_result(filename, mimetype, content, delivery)
