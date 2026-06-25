from __future__ import annotations

from odoo import _, models


class Container(models.Model):
    """Hold mails that could not be routed to any thread."""

    _name = 'muk_mail_route.container'
    _inherit = [
        'mail.thread',
    ]
    _description = 'Message Container'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def message_post(self, *args, **kwargs) -> models.BaseModel:
        """Post a message without subscribing or auto-following recipients."""
        return super(
            Container,
            self.with_context(
                mail_create_nosubscribe=True,
                mail_post_autofollow=False,
            ),
        ).message_post(*args, **kwargs)

    # ----------------------------------------------------------
    # Compute
    # ----------------------------------------------------------

    def _compute_display_name(self) -> None:
        """Label every container record as the message container."""
        self.display_name = _('Message Container')
