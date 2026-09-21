from __future__ import annotations

from odoo import models


class MailThread(models.AbstractModel):
    """Notify the internal followers of a thread on demand."""

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_internal_follower_partners(self) -> models.BaseModel:
        """Return the followers that are backed by an internal user account."""
        return self.sudo().message_partner_ids.filtered(
            lambda partner: partner.main_user_id and not partner.main_user_id.share
        )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def message_post(
        self, *, partner_ids: list[int] | None = None, **kwargs
    ) -> models.BaseModel:
        """Add the internal followers as recipients when the context asks for it."""
        if (
            self.env.context.get('mail_notify_internal_followers')
            and not self.env.user.share
        ):
            partners = self._get_internal_follower_partners() - self.env.user.partner_id
            return self.with_context(
                mail_notify_internal_followers=False
            ).message_post(
                partner_ids=sorted({*(partner_ids or []), *partners.ids}), **kwargs
            )
        return super().message_post(partner_ids=partner_ids, **kwargs)
