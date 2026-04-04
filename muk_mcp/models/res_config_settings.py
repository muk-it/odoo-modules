from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_session_timeout = fields.Integer(
        string="Session Timeout (hours)",
        config_parameter='muk_mcp.session_timeout_hours',
        default=24,
        help="Inactive MCP sessions are cleaned up after this many hours.",
    )

    mcp_log_retention = fields.Integer(
        string="Log Retention (days)",
        config_parameter='muk_mcp.log_autovacuum_days',
        default=30,
        help="Audit logs older than this many days are automatically deleted.",
    )

    mcp_annotate_messages = fields.Boolean(
        string="Annotate Messages",
        config_parameter='muk_mcp.annotate_messages',
        default=True,
        help="When enabled, chatter messages from MCP operations are "
             "annotated with 'via MCP: <key name>' to distinguish "
             "AI-originated changes from manual ones.",
    )
