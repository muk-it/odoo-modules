from __future__ import annotations

from odoo import fields, models


class MailMessage(models.Model):
    """Link messages to the AI session that produced them."""

    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    muk_ai_session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string='MuK AI Session',
        index='btree_not_null',
        ondelete='cascade',
    )
