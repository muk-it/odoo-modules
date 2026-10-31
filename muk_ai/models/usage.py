from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils


class AIUsage(models.Model):
    """One charge of AI spend, kept apart from the chat that caused it."""

    _name = 'muk_ai.usage'
    _description = 'AI Usage'
    _order = 'date desc, id desc'

    # ----------------------------------------------------------
    # Defaults
    # ----------------------------------------------------------

    def _selection_purpose(self) -> list[tuple[str, str]]:
        """Return the purposes of a spend: the model modalities and those addons add."""
        return (
            self.env['muk_ai.model']
            ._fields['modality']
            ._description_selection(self.env)
        )

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

    purpose = fields.Selection(
        selection=lambda self: self._selection_purpose(),
        string='Purpose',
        help='What the spend was for, such as chat, image, decision or embedding.',
        readonly=True,
        index=True,
    )

    res_model = fields.Char(
        string='Origin Model',
        readonly=True,
        index=True,
    )

    res_id = fields.Many2oneReference(
        model_field='res_model',
        string='Origin',
        readonly=True,
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

    @api.model
    def _budget_message(
        self, user: models.BaseModel, currency: str | None = None
    ) -> str | None:
        """Return why ``user`` may spend no more this month, ``None`` while they may.

        The monthly budget of the user comes first, then the one of all users.
        """
        params = self.env['ir.config_parameter'].sudo()
        currency = currency or 'USD'
        user_limit = not user._is_superuser() and (
            user.ai_monthly_budget
            or float(params.get_param('muk_ai.user_monthly_budget') or 0)
        )
        for limit, spender in (
            (user_limit, user),
            (float(params.get_param('muk_ai.monthly_budget') or 0), None),
        ):
            if (
                not limit
                or limit <= 0
                or self.sudo()._spent_this_month(spender) < limit
            ):
                continue
            if spender:
                return _(
                    'Your monthly AI budget of %(amount).2f %(currency)s is '
                    'used up. Ask an administrator to raise it.',
                    amount=limit,
                    currency=currency,
                )
            return _(
                'The monthly AI budget of %(amount).2f %(currency)s for all '
                'users is used up. Ask an administrator to raise it.',
                amount=limit,
                currency=currency,
            )
        return None

    @api.model
    def _check_budget(
        self, user: models.BaseModel | None = None, currency: str | None = None
    ) -> None:
        """Refuse further spend once a monthly budget of the user is used up.

        :raise UserError: when the budget of the user or of all users is spent
        """
        if message := self._budget_message(user or self.env.user, currency):
            raise UserError(message)

    @api.model
    def _charge(
        self,
        model: models.BaseModel,
        usage: dict | None,
        purpose: str,
        user: models.BaseModel | None = None,
        record: models.BaseModel | None = None,
        session: models.BaseModel | None = None,
    ) -> dict:
        """Price a usage payload with ``model`` and book it to the user's ledger.

        :param record: the record the spend was made for
        :return: the input, output and total cost of the payload
        """
        cost = model._compute_usage_cost(usage)
        if cost['total_cost']:
            self.sudo().create(
                {
                    'user_id': (user or self.env.user).id,
                    'session_id': session.id if session else False,
                    'amount': cost['total_cost'],
                    'purpose': purpose,
                    'res_model': record._name if record else False,
                    'res_id': record.id if record else False,
                }
            )
        return cost

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
