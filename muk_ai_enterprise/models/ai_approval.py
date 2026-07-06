from __future__ import annotations

from odoo import api, models

from odoo.addons.muk_ai_enterprise.tools import adapter


class AIApproval(models.Model):
    """Route EE ``ee_action_*`` tool calls through the AI approval gate."""

    _inherit = 'muk_ai.approval'

    # ----------------------------------------------------------
    # Helper Risk
    # ----------------------------------------------------------

    @api.model
    def _assess_ee_action_risk(self, tool_name: str) -> dict | None:
        """Return a risk descriptor when an EE action targets a sensitive model.

        :return: a risk descriptor mirroring the builtin verbs' shape when the
            resolved action writes an ``ai_sensitive`` model, else ``None``
        """
        action = self.env['muk_mcp.tool']._resolve_ee_action(tool_name)
        model_name = action.model_id.model if action else ''
        if not model_name or not self._is_sensitive_model(model_name):
            return None
        label = action.name or tool_name
        return {
            'tool': tool_name,
            'model': model_name,
            'ids': [],
            'method': '',
            'reason': (
                f'{model_name} is flagged sensitive. '
                f'Approve to let the agent run {label}.'
            ),
            'signature': self._signature(tool_name, model_name),
        }

    @api.model
    def _assess_risk(self, tool_name: str, arguments: dict) -> dict | None:
        """Assess EE action risk before delegating to the builtin verb rules."""
        if isinstance(tool_name, str) and tool_name.startswith(adapter.TOOL_PREFIX):
            return self._assess_ee_action_risk(tool_name)
        return super()._assess_risk(tool_name, arguments)
