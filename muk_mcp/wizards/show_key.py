from __future__ import annotations

from odoo import fields, models


class MCPKeyShow(models.AbstractModel):
    """Read-only wizard revealing the plaintext API key a single time."""

    _name = 'muk_mcp.key.show'
    _description = 'Show MCP Key'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    id = fields.Id(
        string='ID',
    )

    key = fields.Char(
        string='API Key',
        readonly=True,
    )
