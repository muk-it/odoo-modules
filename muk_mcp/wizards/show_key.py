from __future__ import annotations

from odoo import fields, models
from odoo.tools import SQL


class MCPKeyShow(models.Model):
    """Read-only wizard revealing the plaintext API key a single time."""

    _name = 'muk_mcp.key.show'
    _description = 'Show MCP Key'
    _explanation = (
        'The dialog that shows a newly created MCP API key once, so the user '
        'can copy it into their AI client.'
    )
    _auto = False
    _table_sql = SQL('(0)')

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
