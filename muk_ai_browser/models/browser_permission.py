from __future__ import annotations

from odoo import api, fields, models


class BrowserPermission(models.Model):
    """Per-user, per-origin browser action permission grant."""

    _name = 'muk_ai_browser.permission'
    _description = 'MuK AI Browser Permission'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade',
    )

    origin = fields.Char(
        string='Origin',
        required=True,
    )

    mode = fields.Selection(
        selection=[
            ('ask', 'Ask Every Time'),
            ('follow_plan', 'Follow Plan'),
        ],
        string='Mode',
        required=True,
        default='ask',
    )

    create_date = fields.Datetime(
        string='Granted On',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mode_for(self, user: models.BaseModel, origin: str | None) -> str:
        """Return the permission mode for a user and page origin.

        :return: ``'follow_plan'`` when the origin was granted, else ``'ask'``
        """
        if not user or not origin:
            return 'ask'
        record = self.sudo().search(
            [
                ('user_id', '=', user.id),
                ('origin', '=', origin),
            ],
            limit=1,
        )
        return record.mode if record else 'ask'

    @api.model
    def _grant(self, user: models.BaseModel, origin: str | None) -> models.BaseModel:
        """Grant ``follow_plan`` to a user for an origin, creating or updating the row.

        :return: the granted permission record (empty when ``origin`` is missing)
        """
        if not user or not origin:
            return self.browse()
        record = self.sudo().search(
            [
                ('user_id', '=', user.id),
                ('origin', '=', origin),
            ],
            limit=1,
        )
        if record:
            record.mode = 'follow_plan'
            return record
        return self.sudo().create(
            {
                'user_id': user.id,
                'origin': origin,
                'mode': 'follow_plan',
            },
        )
