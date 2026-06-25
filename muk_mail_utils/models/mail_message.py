from __future__ import annotations

import textwrap

from odoo import api, fields, models


class MailMessage(models.Model):
    """Add a shortened display content derived from subject and preview."""

    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    display_content = fields.Char(
        compute='_compute_display_content',
        string='Display Content',
        compute_sudo=True,
        readonly=True,
        store=True,
    )

    # ----------------------------------------------------------
    # Override Fields
    # ----------------------------------------------------------

    preview = fields.Char(
        readonly=True,
        store=True,
    )

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    @api.depends('subject', 'preview')
    def _compute_display_content(self) -> None:
        """Join subject and preview into a single shortened display string."""
        for record in self:
            display_content = ' | '.join(
                text for text in [record.subject, record.preview] if text
            )
            record.display_content = textwrap.shorten(display_content, 100)
