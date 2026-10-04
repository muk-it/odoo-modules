from __future__ import annotations

from typing import Any

from odoo import api, fields, models

from odoo.addons.mail.tools.discuss import Store


class MailMessage(models.Model):
    """Store and expose the originating MCP key name on messages."""

    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_name = fields.Char(
        string='MCP Key',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _store_message_fields(self, res: Store.FieldList, **kwargs: Any) -> None:
        """Send the MCP key name to the web client with the message."""
        super()._store_message_fields(res, **kwargs)
        res.attr('mcp_name')

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict[str, Any]]) -> models.BaseModel:
        """Default ``mcp_name`` from the context when an MCP key is active."""
        if mcp_name := self.env.context.get('mcp_name'):
            for vals in vals_list:
                vals.setdefault('mcp_name', mcp_name)
        return super().create(vals_list)
