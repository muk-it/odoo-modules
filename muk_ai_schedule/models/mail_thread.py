from __future__ import annotations

from odoo import models


class MailThread(models.AbstractModel):
    """Wake the AI chats that wait for a message on a record."""

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _message_post_after_hook(
        self, message: models.BaseModel, msg_values: dict
    ) -> None:
        """Hand a posted comment or email to the chats waiting for one."""
        super()._message_post_after_hook(message, msg_values)
        if message.message_type in ('comment', 'email'):
            self.env['muk_ai.session']._wake_on_message(message)
