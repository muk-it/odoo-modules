from __future__ import annotations

import contextlib
from typing import Any

from markupsafe import Markup

from odoo import api, fields, models
from odoo.api import Environment
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import json as safe_json
from odoo.tools.safe_eval import safe_eval, test_python_expr

from odoo.addons.muk_mcp.tools.logger import LoggerProxy


class MCPSandbox(models.AbstractModel):
    """Database-defined MCP entry whose Python code runs in a sandbox."""

    _name = 'muk_mcp.sandbox'
    _description = 'MCP Sandbox'
    _order = 'sequence, name'
    _code_field = 'code'
    _list_changed = 'notifications/tools/list_changed'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
    )

    active = fields.Boolean(
        string='Active',
        default=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    description = fields.Text(
        string='Description',
        required=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_eval_context(
        self,
        arguments: dict[str, Any],
        env: Environment,
    ) -> dict[str, Any]:
        """Build the sandbox namespace the code runs in."""
        return {
            'env': env,
            'arguments': arguments,
            'json': safe_json,
            'Markup': Markup,
            'callable': callable,
            'getattr': getattr,
            'hasattr': hasattr,
            'UserError': UserError,
            'logger': LoggerProxy(f'odoo.addons.{self._name} ({self.name})'),
        }

    def _run(self, arguments: dict[str, Any], env: Environment) -> Any:
        """Evaluate the code in the sandbox and return what it set as ``result``."""
        eval_context = self._get_eval_context(arguments, env)
        safe_eval(self[self._code_field].strip(), eval_context, mode='exec')
        return eval_context.get('result')

    def _notify_list_changed(self) -> None:
        """Tell the open MCP sessions that the listing changed."""
        with contextlib.suppress(Exception):
            self.env['muk_mcp.notification'].push_to_all_sessions(self._list_changed)

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains(lambda self: [self._code_field])
    def _check_code(self) -> None:
        """Validate that the code is safe Python."""
        for record in self.sudo().filtered(self._code_field):
            if message := test_python_expr(
                expr=record[self._code_field].strip(), mode='exec'
            ):
                raise ValidationError(message)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict[str, Any]]) -> MCPSandbox:
        """Create entries and notify the sessions that the listing changed."""
        records = super().create(vals_list)
        self._notify_list_changed()
        return records

    def write(self, vals: dict[str, Any]) -> bool:
        """Write entries and notify the sessions that the listing changed."""
        result = super().write(vals)
        self._notify_list_changed()
        return result

    def unlink(self) -> bool:
        """Delete entries and notify the sessions that the listing changed."""
        result = super().unlink()
        self._notify_list_changed()
        return result
