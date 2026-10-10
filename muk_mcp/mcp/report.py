from __future__ import annotations

import re
from typing import Any

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    delivery_field,
    ids_field,
)

REPORT_FORMATS = {
    'pdf': ('application/pdf', 'pdf'),
    'text': ('text/plain', 'txt'),
    'html': ('text/html', 'html'),
}


class MCPMixin(models.AbstractModel):
    """Add the MCP report-printing tool to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_report(self, report_ref: str | int) -> models.BaseModel:
        """Resolve a report reference given as an id, an xmlid, or a ``report_name`` to its ``ir.actions.report``."""
        ref = str(report_ref).strip()
        if ref.isdigit():
            return self.env['ir.actions.report'].browse(int(ref)).exists()
        if '.' in ref:
            report = self.env.ref(ref, raise_if_not_found=False)
            if report and report._name == 'ir.actions.report':
                return report
        return self.env['ir.actions.report'].search(
            [('report_name', '=', ref)],
            limit=1,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='print_report',
        description=(
            'Render an Odoo report for one or more records. Accepts a report '
            'xmlid (e.g. "sale.action_report_saleorder"), a report_name '
            '(e.g. "sale.report_saleorder"), or the numeric id of an '
            'ir.actions.report.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'report_ref': {
                    'type': ['string', 'integer'],
                    'description': (
                        'Report xmlid, report_name, or id of the ir.actions.report to render.'
                    ),
                },
                'ids': ids_field('render'),
                'delivery': delivery_field(),
                'context': context_field(),
            },
            'required': ['report_ref', 'ids'],
        },
        category='read',
    )
    def _mcp_print_report(
        self,
        report_ref: str | int,
        ids,
        delivery: str = 'inline',
    ) -> dict[str, Any]:
        """Render the referenced report for ``ids`` and return the file.

        :raise UserError: when ``ids`` is empty or the report cannot be resolved.
        """
        if not (report := self._resolve_report(report_ref)):
            raise UserError(_('Report %r not found.', report_ref))
        records = self._mcp_records(report.model, ids)
        content, report_type = report._render(report.report_name, records.ids)
        mimetype, extension = REPORT_FORMATS.get(
            report_type, ('application/octet-stream', report_type)
        )
        name = report.name or report.report_name or 'report'
        if report.print_report_name and len(records) == 1:
            name = safe_eval(
                report.print_report_name, {'object': records, 'time': time}
            )
        if isinstance(content, str):
            content = content.encode()
        filename = '%s.%s' % (re.sub(r'[\s/\\]+', '_', name), extension)
        return self._mcp_file_result(filename, mimetype, content, delivery)
