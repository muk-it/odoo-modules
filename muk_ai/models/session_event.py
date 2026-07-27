from __future__ import annotations

from odoo import fields, models


class AISessionEvent(models.Model):
    """Ordered append-only event in a session's replay log."""

    _name = 'muk_ai.session.event'
    _description = 'AI Session Event'
    _order = 'session_id, sequence, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='Session',
        required=True,
        index=True,
        ondelete='cascade',
    )

    sequence = fields.Integer(
        string='Sequence',
        required=True,
        default=0,
        index=True,
    )

    kind = fields.Char(
        string='Kind',
        required=True,
        index=True,
    )

    payload = fields.Json(
        string='Payload',
        required=True,
    )

    at = fields.Datetime(
        string='At',
        required=True,
        default=fields.Datetime.now,
    )

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    _sql_constraints = [
        (
            'unique_session_sequence',
            'unique(session_id, sequence)',
            'Session event sequence must be unique per session.',
        ),
    ]
