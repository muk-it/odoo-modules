from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Any

from odoo import SUPERUSER_ID, api, fields, models, tools
from odoo.http import request
from odoo.modules.registry import Registry
from odoo.tools.misc import mute_logger


class MCPLog(models.Model):
    """Audit trail of MCP requests with status, payloads and duration."""

    _name = 'muk_mcp.log'
    _description = 'MCP Audit Log'
    _explanation = (
        'One request an MCP client sent: the tool or method, the user and '
        'key, the arguments, the outcome, the duration and the record it '
        'touched. Use it to see what an AI assistant did in the database and '
        'why a call failed.'
    )
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    key_name = fields.Char(
        string='API Key',
        readonly=True,
        index=True,
        help='Label of the API key used.',
    )

    key_prefix = fields.Char(
        string='Key Prefix',
        readonly=True,
        help='First characters of the API key used.',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        readonly=True,
        index=True,
        ondelete='set null',
    )

    method = fields.Char(
        string='Method',
        readonly=True,
        index=True,
    )

    tool_name = fields.Char(
        string='Tool',
        readonly=True,
        index=True,
    )

    model_name = fields.Char(
        string='Model',
        readonly=True,
    )

    res_id = fields.Integer(
        string='Record ID',
        readonly=True,
    )

    res_ids = fields.Json(
        string='Record IDs',
        readonly=True,
    )

    request_data = fields.Text(
        string='Request',
        readonly=True,
    )

    response_data = fields.Text(
        string='Response',
        readonly=True,
    )

    ip_address = fields.Char(
        string='IP Address',
        readonly=True,
    )

    duration_ms = fields.Integer(
        string='Duration (ms)',
        readonly=True,
    )

    status = fields.Selection(
        selection=[
            ('ok', 'OK'),
            ('error', 'Error'),
            ('denied', 'Denied'),
            ('rate_limited', 'Rate Limited'),
        ],
        string='Status',
        readonly=True,
        index=True,
    )

    error_message = fields.Text(
        string='Error',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _retention_limit(self) -> datetime:
        """Return the moment before which audit records are deleted."""
        days = (
            self.env['ir.config_parameter']
            .sudo()
            .get_int(
                'muk_mcp.log_autovacuum_days',
                int(tools.config.get('mcp_log_autovacuum_days', 30)),
            )
        )
        return fields.Datetime.subtract(fields.Datetime.now(), days=days)

    @api.model
    def _request_values(self) -> dict[str, Any]:
        """Return the address and credential of the HTTP request being served."""
        if not request:
            return {}
        values = {'ip_address': request.httprequest.remote_addr}
        if key := getattr(request, '_mcp_key', None):
            values.update(key_name=key.name, key_prefix=key.key_prefix)
        return values

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_record(self) -> dict[str, Any] | None:
        """Open the single logged record, or warn when it was deleted.

        :return: a form action, a notification action, or ``None`` when the
            log carries no single-record reference
        """
        self.ensure_one()
        if not self.model_name or not self.res_id:
            return None
        if (
            not self.env[self.model_name]
            .sudo()
            .search_count(
                [('id', '=', self.res_id)],
                limit=1,
            )
        ):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Record not found',
                    'message': f'{self.model_name}({self.res_id}) no longer exists.',
                    'type': 'warning',
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_records(self) -> dict[str, Any] | None:
        """Open the logged records in a list view.

        :return: a list action, or ``None`` when the log carries no
            multi-record reference
        """
        self.ensure_one()
        if self.model_name and self.res_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': self.model_name,
                'res_model': self.model_name,
                'domain': [('id', 'in', self.res_ids)],
                'views': [(False, 'list'), (False, 'form')],
                'target': 'current',
            }
        return None

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def log(self, **values: Any) -> None:
        """Write an audit entry on an independent cursor, never raising.

        The address and credential of the current request fill in what
        ``values`` leaves out.
        """
        with (
            contextlib.suppress(Exception),
            mute_logger('odoo.sql_db'),
            Registry(
                self.env.cr.dbname,
            ).cursor() as cr,
        ):
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['muk_mcp.log'].create({**self._request_values(), **values})

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('method', 'tool_name')
    def _compute_display_name(self) -> None:
        """Name each entry after its method and, for a tool call, the tool."""
        for record in self:
            parts = (record.method, record.tool_name)
            record.display_name = ' - '.join(part for part in parts if part)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_logs(self) -> None:
        """Delete audit-log rows older than the configured retention period."""
        domain = [('create_date', '<', self._retention_limit())]
        while batch := self.search(domain, limit=5000):
            batch.unlink()
            self.env.cr.commit()
