from __future__ import annotations

from urllib.parse import urlsplit

from odoo import _, api, models


class AIApproval(models.Model):
    """Show the user what a browser call or plan does before approving it."""

    _inherit = 'muk_ai.approval'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _build_preview(self, tool_name: str, arguments: dict) -> dict | None:
        """Preview a browser call as its arguments, a plan as its steps and sites."""
        if tool_name == 'browser_propose_plan':
            return self._build_plan_preview(arguments)
        if not self.env['muk_ai.session']._browser_tool(tool_name):
            return super()._build_preview(tool_name, arguments)
        return {
            'kind': 'create',
            'title': arguments.get('element') or tool_name,
            'properties': [
                self._build_property(None, key, value)
                for key, value in arguments.items()
                if key not in ('ref', 'trusted', 'attachment_id')
            ],
        }

    @api.model
    def _build_plan_preview(self, arguments: dict) -> dict:
        """Preview a proposed browser plan as its numbered steps and its sites."""
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
                            urlsplit(
                                self.env['muk_ai.session']._browser_origin_of(origin)
                            ).netloc
                            for origin in arguments.get('origins') or []
                        )
                    ),
                ),
            ],
        }
