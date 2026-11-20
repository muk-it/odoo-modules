from __future__ import annotations

from markupsafe import Markup

from odoo import _, api, models


class MailThread(models.AbstractModel):
    """Route unroutable mails into the container and move messages between records."""

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

    def _mail_route_receive(
        self, messages, internal: bool = False, notify: bool = False
    ) -> None:
        """Move the messages, and the attachments only they use, onto the record."""
        messages = messages.sudo()
        attachments = (
            messages.attachment_ids
            - messages.search(
                [
                    ('attachment_ids', 'in', messages.attachment_ids.ids),
                    ('id', 'not in', messages.ids),
                ]
            ).attachment_ids
        )
        for model in set(messages.filtered('model').mapped('model')):
            sources = (
                self.env[model]
                .sudo()
                .browse(messages.filtered(lambda m: m.model == model).mapped('res_id'))
            )
            if 'message_main_attachment_id' in sources._fields:
                sources.filtered(
                    lambda source: source.message_main_attachment_id in attachments
                ).message_main_attachment_id = False
        (
            messages.filtered(lambda m: m.parent_id and m.parent_id not in messages)
            | messages.search(
                [
                    ('parent_id', 'in', messages.ids),
                    ('id', 'not in', messages.ids),
                ]
            )
        ).parent_id = False
        messages.write(
            {
                'model': self._name,
                'res_id': self.id,
                'record_name': self.display_name,
                'record_company_id': self._mail_get_companies(default=self.env.company)[
                    self.id
                ].id,
                'record_alias_domain_id': self.sudo()
                ._mail_get_alias_domains(default_company=self.env.company)[self.id]
                .id,
            }
        )
        attachments.write({'res_model': self._name, 'res_id': self.id})
        if internal:
            messages.is_internal = True
        if notify:
            for message in messages.with_env(self.env):
                self._notify_thread(message)

    def _mail_route_log(self, target) -> None:
        """Log the move of messages on the record and on the target."""
        self._message_log(
            body=Markup(_('Messages moved to %s')) % target._get_html_link()
        )
        target._message_log(
            body=Markup(_('Messages moved from %s')) % self._get_html_link()
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
