import contextlib

from odoo import api, tools, fields, models, SUPERUSER_ID
from odoo.modules.registry import Registry


class MCPLog(models.Model):

    _name = 'muk_mcp.log'
    _description = "MCP Audit Log"
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    key_id = fields.Many2one(
        comodel_name='muk_mcp.key',
        string="API Key",
        readonly=True,
        index=True,
        ondelete='set null',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="User",
        readonly=True,
        index=True,
        ondelete='set null',
    )

    method = fields.Char(
        string="Method",
        readonly=True,
        index=True,
    )

    tool_name = fields.Char(
        string="Tool",
        readonly=True,
        index=True,
    )

    model_name = fields.Char(
        string="Model",
        readonly=True,
    )

    duration_ms = fields.Integer(
        string="Duration (ms)",
        readonly=True,
    )

    status = fields.Selection(
        selection=[
            ('ok', "OK"),
            ('error', "Error"),
            ('denied', "Denied"),
            ('rate_limited', "Rate Limited"),
        ],
        string="Status",
        readonly=True,
        index=True,
    )

    error_message = fields.Text(
        string="Error",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def log(self, **values):
        with contextlib.suppress(Exception), mute_logger('odoo.sql_db'), Registry(
                self.env.cr.dbname
            ).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['muk_mcp.log'].create(values)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_logs(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'muk_mcp.log_autovacuum_days',
            tools.config.get('mcp_log_autovacuum_days', 30)
        ))
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        self.search([('create_date', '<', limit)]).unlink()
