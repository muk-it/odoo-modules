from odoo import fields, models

from odoo.addons.base.models.res_users import check_identity


class ResUsers(models.Model):

    _inherit = 'res.users'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'mcp_key_ids',
            'mcp_session_ids',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            'mcp_key_ids',
            'mcp_session_ids',
        ]

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_key_ids = fields.One2many(
        comodel_name='muk_mcp.key',
        inverse_name='user_id',
        string="MCP Keys",
    )

    mcp_session_ids = fields.One2many(
        comodel_name='muk_mcp.session',
        inverse_name='user_id',
        string="MCP Sessions",
        domain=[('active', '=', True)],
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    @check_identity
    def action_generate_mcp_key(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New MCP Key',
            'res_model': 'muk_mcp.generate_key',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_revoke_mcp_sessions(self):
        sessions = self.env['muk_mcp.session'].sudo().search([
            ('user_id', '=', self.id),
            ('active', '=', True),
        ])
        sessions.write({'active': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
