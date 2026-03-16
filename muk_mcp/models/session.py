import uuid

from odoo import api, tools, fields, models


class MCPSession(models.Model):

    _name = 'muk_mcp.session'
    _description = "MCP Session"
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    session_id = fields.Char(
        string="Session ID",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: str(uuid.uuid4()),
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="User",
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )

    initialized = fields.Boolean(
        string="Initialized",
        default=False,
    )

    last_activity = fields.Datetime(
        string="Last Activity",
        default=fields.Datetime.now,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_revoke(self):
        self.write({'active': False})

    def action_touch(self):
        if not self:
            return
        cr = self.env.cr
        try:
            cr.execute("SAVEPOINT session_touch")
            cr.execute(
                """
                UPDATE muk_mcp_session
                   SET last_activity = NOW() AT TIME ZONE 'UTC',
                       write_date = NOW() AT TIME ZONE 'UTC',
                       write_uid = %s
                 WHERE id IN %s
                """,
                (self.env.uid, tuple(self.ids)),
            )
            cr.execute("RELEASE SAVEPOINT session_touch")
            self.invalidate_recordset([
                'last_activity', 'write_date', 'write_uid',
            ])
        except Exception:
            cr.execute("ROLLBACK TO SAVEPOINT session_touch")
            cr.execute("RELEASE SAVEPOINT session_touch")

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_sessions(self):
        hours = int(self.env['ir.config_parameter'].sudo().get_param(
            'muk_mcp.session_timeout_hours',
            tools.config.get('mcp_session_timeout_hours', 24)
        ))
        limit = fields.Datetime.subtract(fields.Datetime.now(), hours=hours)
        self.search([('last_activity', '<', limit)]).unlink()
