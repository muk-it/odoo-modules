from __future__ import annotations

from odoo import api, fields, models
from odoo.tools import date_utils


class AIUsage(models.Model):
    """One charge of AI spend, kept apart from the chat that caused it."""

    _name = 'muk_ai.usage'
    _description = 'AI Usage'
    _order = 'date desc, id desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    date = fields.Datetime(
        string='Date',
        readonly=True,
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        readonly=True,
        required=True,
        index=True,
        ondelete='cascade',
    )

    session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Chat',
        readonly=True,
        ondelete='set null',
    )

    amount = fields.Float(
        string='Amount',
        help='Cost of the charge, in the price currency of the model.',
        readonly=True,
        digits=(12, 6),
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _spent_this_month(self, user: models.BaseModel | None = None) -> float:
        """Return what one user, or everyone without ``user``, spent this month."""
        domain = [('date', '>=', date_utils.start_of(fields.Datetime.now(), 'month'))]
        if user:
            domain.append(('user_id', '=', user.id))
        [(amount,)] = self._read_group(domain, aggregates=['amount:sum'])
        return amount or 0.0

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _gc_usage(self) -> None:
        """Delete the usage of the months before the ones the settings keep."""
        params = self.env['ir.config_parameter'].sudo()
        months = (
            max(int(params.get_param('muk_ai.usage_retention_months') or 0), 0) or 6
        )
        start = date_utils.start_of(fields.Datetime.now(), 'month')
        cutoff = date_utils.subtract(start, months=months)
        self.sudo().search([('date', '<', cutoff)]).unlink()
