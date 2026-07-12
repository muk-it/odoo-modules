from __future__ import annotations

from typing import Any

from odoo import _, api, models
from odoo.exceptions import AccessError


class MCPMixin(models.AbstractModel):
    """Wrap the MCP report tool to enforce the allowlist and record domains."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mcp_print_report(self, report_ref: str | int, ids) -> dict[str, Any]:
        """Assert model and record access before rendering the referenced report."""
        report = self._resolve_report(report_ref)
        if report:
            model = report.model
            if not self.env['muk_mcp_access.model']._is_model_allowed(model, 'read'):
                raise AccessError(
                    _(
                        'Model %(model)r is not accessible via MCP.',
                        model=model,
                    )
                )
            self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_print_report(report_ref, ids)
