from __future__ import annotations

import base64
from typing import Any

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import context_field, ids_field

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
        if isinstance(report_ref, int):
            return self.env['ir.actions.report'].browse(
                report_ref,
            )
        if '.' in (ref := (report_ref or '').strip()):
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
            'Render an Odoo report for one or more records and return the '
            'binary as base64. Accepts a report xmlid (e.g. '
            '"sale.action_report_saleorder"), a report_name '
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
    ) -> dict[str, Any]:
        """Render the referenced report for ``ids`` and return its filename, mimetype and base64 content.

        :raise UserError: when ``ids`` is empty or the report cannot be resolved.
        """
        if not (report := self._resolve_report(report_ref)):
            raise UserError(self.env._('Report %r not found.', report_ref))
        records = self._mcp_records(report.model, ids)
        content, report_type = report._render(report, records.ids)
        mimetype, extension = REPORT_FORMATS.get(
            report_type, ('application/octet-stream', report_type)
        )
        name = report.name or report.report_name or 'report'
        if isinstance(content, str):
            content = content.encode()
        return {
            'filename': '%s.%s' % (name.replace(' ', '_'), extension),
            'mimetype': mimetype,
            'content_base64': base64.b64encode(content).decode(),
        }
