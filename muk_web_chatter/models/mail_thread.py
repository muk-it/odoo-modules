from __future__ import annotations

from odoo import models


class MailThread(models.AbstractModel):
    """Notify the internal followers of a thread on demand."""

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def message_post(
        self, *, partner_ids: list[int] | None = None, **kwargs
    ) -> models.BaseModel:
        """Add the internal followers as recipients when the context asks for it."""
        thread = self
        if (
            self.env.context.get('mail_notify_internal_followers')
            and not self.env.user.share
        ):
            partners = self.sudo().message_partner_ids.filtered(
                lambda partner: partner.main_user_id and not partner.main_user_id.share
            )
            partner_ids = sorted(
                {*(partner_ids or []), *(partners - self.env.user.partner_id).ids}
            )
            thread = self.with_context(mail_notify_internal_followers=False)
        return super(MailThread, thread).message_post(partner_ids=partner_ids, **kwargs)
