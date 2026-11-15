from __future__ import annotations

from urllib.parse import urlsplit

from odoo import _, api, models


class AIApproval(models.Model):
    """Show the user the steps and sites of a browser plan before approving it."""

    _inherit = 'muk_ai.approval'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _build_preview(self, tool_name: str, arguments: dict) -> dict | None:
        """Preview a proposed browser plan as its numbered steps and its sites."""
        if tool_name != 'browser_propose_plan':
            return super()._build_preview(tool_name, arguments)
        session = self.env['muk_ai.session']
        return {
            'kind': 'create',
            'title': arguments.get('summary') or '',
            'properties': [
                self._build_property(
                    None,
                    _('Steps'),
                    '\n'.join(
                        f'{index}. {step}'
                        for index, step in enumerate(arguments.get('steps') or [], 1)
                    ),
                ),
                self._build_property(
                    None,
                    _('Sites'),
                    ', '.join(
                        dict.fromkeys(
                            urlsplit(session._browser_origin_of(origin)).netloc
                            for origin in arguments.get('origins') or []
                        )
                    ),
                ),
            ],
        }
