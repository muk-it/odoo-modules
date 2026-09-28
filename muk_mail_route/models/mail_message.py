from __future__ import annotations

import json

from lxml import etree

from odoo import api, fields, models


class MailMessage(models.Model):
    """Add per-configuration routing buttons to the failed-message list."""

    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_route_configurations(self) -> models.BaseModel:
        """Return the routing rules on models the current user may read."""
        configurations = self.env['muk_mail_route.configuration']
        if not self.env.user.has_group('base.group_erp_manager'):
            return configurations
        return configurations.search([], order='sequence DESC').filtered(
            lambda configuration: self.env[configuration.model].has_access('read')
        )

    @api.model
    def _get_view_cache_key(
        self, view_id=None, view_type: str = 'form', **options
    ) -> tuple:
        """Extend the cache key with the routing rules the user may use."""
        key = super()._get_view_cache_key(view_id, view_type, **options)
        failed_view = self.env.ref(
            'muk_mail_route.view_mail_message_failed_list', raise_if_not_found=False
        )
        if failed_view and view_id == failed_view.id:
            key += (tuple(self._get_route_configurations().ids),)
        return key

    @api.model
    def _get_view(self, view_id=None, view_type: str = 'form', **options) -> tuple:
        """Inject a routing button per configuration into the failed list."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view == self.env.ref(
            'muk_mail_route.view_mail_message_failed_list', raise_if_not_found=False
        ):
            configurations = self._get_route_configurations()
            for node in arch.xpath(".//button[@name='action_route_message']"):
                for configuration in configurations:
                    button = etree.Element(
                        'button',
                        {
                            'class': 'btn-secondary',
                            'string': configuration.name,
                            'name': 'action_route_message',
                            'type': 'object',
                            'groups': 'base.group_erp_manager',
                            'context': json.dumps(
                                {
                                    'default_configuration_id': configuration.id,
                                }
                            ),
                        },
                    )
                    node.addnext(button)
        return arch, view

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_route_message(self) -> dict:
        """Open the routing wizard pre-filled with the selected messages."""
        return {
            'name': self.env._('Route Message'),
            'res_model': 'muk_mail_route.router',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_message_ids': [fields.Command.set(self.ids)],
            },
        }
