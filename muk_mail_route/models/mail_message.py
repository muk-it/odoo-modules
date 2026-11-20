from __future__ import annotations

import json
import textwrap

from lxml import etree

from odoo import _, api, fields, models


class MailMessage(models.Model):
    """Add per-configuration routing buttons to the failed-message list."""

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

    preview = fields.Char(
        readonly=True,
        store=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_route_configurations(self) -> models.BaseModel:
        """Return the routing rules on models the current user may read."""
        return (
            self.env['muk_mail_route.configuration']
            .search([], order='sequence DESC')
            .filtered(
                lambda configuration: self.env[configuration.model].check_access_rights(
                    'read', raise_exception=False
                )
            )
        )

    @api.model
    def _get_view_cache_key(
        self, view_id=None, view_type: str = 'form', **options
    ) -> tuple:
        """Extend the cache key with the user-dependent routing dimensions."""
        key = super()._get_view_cache_key(view_id, view_type, **options)
        failed_view = self.env.ref(
            'muk_mail_route.view_mail_message_failed_list', raise_if_not_found=False
        )
        if failed_view and view_id == failed_view.id:
            key += (
                self.env.user.has_group('base.group_erp_manager'),
                self.env['ir.model.access']._get_allowed_models(),
            )
        return key

    @api.model
    def _get_view(self, view_id=None, view_type: str = 'form', **options) -> tuple:
        """Inject a routing button per configuration into the failed list."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if self.env.user.has_group('base.group_erp_manager') and view == self.env.ref(
            'muk_mail_route.view_mail_message_failed_list'
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

    @api.model
    def get_route_configurations(self) -> list[dict]:
        """Return the id and name of the routing rules the current user may use."""
        return self._get_route_configurations().sorted('sequence').read(['name'])

    def action_route_message(self) -> dict:
        """Open the routing wizard pre-filled with the selected messages."""
        return {
            'name': _('Route Message'),
            'res_model': 'muk_mail_route.router',
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_message_ids': [fields.Command.set(self.ids)],
            },
        }

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
