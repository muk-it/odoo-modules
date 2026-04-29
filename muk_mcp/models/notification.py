import json
import uuid

from odoo import api, fields, models, tools


class MCPNotification(models.Model):

    _name = 'muk_mcp.notification'
    _description = "MCP Notification"
    _order = 'id asc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    session_id = fields.Many2one(
        comodel_name='muk_mcp.session',
        string="Session",
        required=True,
        index=True,
        ondelete='cascade',
    )

    event_id = fields.Char(
        string="Event ID",
        required=True,
        index=True,
    )

    method = fields.Char(
        string="Method",
        required=True,
    )

    params = fields.Text(
        string="Params",
    )

    delivered = fields.Boolean(
        string="Delivered",
        default=False,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def push_to_all_sessions(self, method, params=None):
        sessions = self.env['muk_mcp.session'].sudo().search([
            ('active', '=', True),
            ('initialized', '=', True),
        ])
        if not sessions:
            return
        vals_list = [
            {
                'session_id': session.id,
                'event_id': str(uuid.uuid4()),
                'method': method,
                'params': json.dumps(params or {}),
            }
            for session in sessions
        ]
        self.sudo().create(vals_list)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def init(self):
        super().init()
        tools.create_index(
            self.env.cr,
            'muk_mcp_notification_undelivered_idx',
            self._table,
            ['session_id', 'id'],
            where='delivered IS NOT TRUE',
        )

    @api.autovacuum
    def _autovacuum_notifications(self):
        delivered_limit = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        stale_limit = fields.Datetime.subtract(fields.Datetime.now(), days=7)
        domain = [
            '|',
            '&', ('delivered', '=', True), ('create_date', '<', delivered_limit),
            '&', ('delivered', '=', False), ('create_date', '<', stale_limit),
        ]
        while batch := self.search(domain, limit=5000):
            batch.unlink()
            self.env.cr.commit()
