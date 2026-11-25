from __future__ import annotations

import json
from typing import Any

from odoo import api, models
from odoo.api import Environment

from odoo.addons.muk_mcp.core.tool import get_tool_index


class MCPTool(models.Model):
    """Carry the tool category and the answer of the user for access enforcement."""

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_confirmation_target(self, arguments: Any) -> tuple[Any, Any]:
        """Return the model and the record ids a call names."""
        if not isinstance(arguments, dict):
            return None, None
        return arguments.get('model'), arguments.get('ids') or arguments.get('id')

    @api.model
    def _call_result(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> dict[str, Any]:
        """Redeem the answer a retried call carries and keep a question it raises.

        The environment holds an elicitation only within a ``tools/call`` request,
        and one that is already answered within a nested call.
        """
        elicitation = env.context.get('mcp_elicitation')
        if not elicitation or 'answer' in elicitation:
            return super()._call_result(name, arguments, env, enforce_scope)
        questions = env['muk_mcp_access.confirmation']
        digest = questions._get_digest(elicitation['principal'], name, arguments)
        redeemed = questions._redeem(elicitation['state'], digest)
        elicitation = {
            **elicitation,
            'answer': elicitation['action'] if redeemed else None,
            'call': f'{name} {json.dumps(arguments, ensure_ascii=False)}'[:1000],
            'target': self._get_confirmation_target(arguments),
        }
        env = env(context={**env.context, 'mcp_elicitation': elicitation})
        result = super()._call_result(name, arguments, env, enforce_scope)
        if result.get('resultType') == 'input_required':
            questions._ask(result['requestState'], digest)
        return result

    @api.model
    def _call(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Pin the tool's category in the environment the tool body receives.

        The context carries it without a bound request and through nested
        calls; what a caller supplies for it or the elicitation is dropped. A
        payload that is not a JSON object passes untouched for the base to reject.
        """
        if entry := get_tool_index(env).get(name):
            if isinstance(arguments, dict):
                arguments = dict(arguments)
                if isinstance(context := arguments.get('context'), dict):
                    arguments['context'] = {
                        key: value
                        for key, value in context.items()
                        if key not in ('mcp_tool_category', 'mcp_elicitation')
                    }
            env = env(context={**env.context, 'mcp_tool_category': entry['category']})
        return super()._call(name, arguments, env, enforce_scope)
