from __future__ import annotations

from odoo import fields, models


class BaseAutomation(models.Model):
    """Set the user the AI agent steps of an automation rule run as."""

    _inherit = 'base.automation'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    agent_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Run Agents As',
        help=(
            'User whose access rights the chats of the AI agent steps run with, '
            'whoever triggers the rule.'
        ),
        default=lambda self: self.env.user,
        domain=[('share', '=', False)],
    )
