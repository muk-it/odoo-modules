# Copyright 2026, Jarsa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    oauth_token_ids = fields.One2many(
        comodel_name="muk_mcp.oauth.token",
        inverse_name="user_id",
        string="OAuth Connections",
        domain=[("revoked", "=", False)],
    )

    @property
    def SELF_READABLE_FIELDS(self):  # pylint: disable=invalid-name
        return super().SELF_READABLE_FIELDS + ["oauth_token_ids"]
