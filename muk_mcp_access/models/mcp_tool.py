from __future__ import annotations

from typing import Any

from odoo import api, models
from odoo.api import Environment

from odoo.addons.muk_mcp.core.tool import get_tool_index


class MCPTool(models.Model):
    """Carry the current tool category in the context for access enforcement."""

    _inherit = 'muk_mcp.tool'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _call(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Pin the tool's category in the environment the tool body receives.

        The category travels in the context instead of on the HTTP request so
        it also applies when no request is bound (cron jobs, direct ORM calls)
        and so nested tool calls cannot downgrade their caller. A caller
        supplied ``mcp_tool_category`` in the tool ``context`` argument is
        dropped, since :meth:`_execute` merges that override on top. A payload
        that is not a JSON object is passed through untouched so the base
        implementation can reject and audit it.
        """
        if entry := get_tool_index(env).get(name):
            if isinstance(arguments, dict):
                arguments = dict(arguments)
                if isinstance(context := arguments.get('context'), dict):
                    arguments['context'] = {
                        key: value
                        for key, value in context.items()
                        if key != 'mcp_tool_category'
                    }
            env = env(context={**env.context, 'mcp_tool_category': entry['category']})
        return super()._call(name, arguments, env, enforce_scope)
