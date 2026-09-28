from __future__ import annotations

from odoo import api, models


class MailThread(models.AbstractModel):
    """Route unroutable mails into the dedicated failure container."""

    _inherit = 'mail.thread'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_failed_route_container(self) -> models.BaseModel:
        """Return the singleton container, creating it without followers."""
        model_ctx = (
            self.env['muk_mail_route.container']
            .sudo()
            .with_context(
                mail_create_nosubscribe=True,
                mail_post_autofollow=False,
                mail_create_nolog=True,
            )
        )
        container = model_ctx.search([], limit=1)
        if not container:
            container = model_ctx.create({})
        if container.message_follower_ids:
            container.message_follower_ids.unlink()
        return container

    @api.model
    def _get_failed_message_route(self, message, message_dict, custom_values) -> tuple:
        """Build a route binding the failed message to the container."""
        container = self._get_failed_route_container()
        user = self._mail_find_user_for_gateway(message_dict['email_from'])
        message_dict.pop('parent_id', None)
        return self._routing_check_route(
            message,
            message_dict,
            (
                container._name,
                container.id,
                custom_values,
                user.id if user else self.env.uid,
                None,
            ),
            raise_exception=True,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def message_route(
        self, message, message_dict, model=None, thread_id=None, custom_values=None
    ) -> list:
        """Fall back to the failure container when no route is found."""
        res = []
        try:
            res = super().message_route(
                message,
                message_dict,
                model=model,
                thread_id=thread_id,
                custom_values=custom_values,
            )
        except ValueError:
            route = self._get_failed_message_route(message, message_dict, custom_values)
            return [route]
        else:
            if not res:
                route = self._get_failed_message_route(
                    message, message_dict, custom_values
                )
                return [route]
        return res
