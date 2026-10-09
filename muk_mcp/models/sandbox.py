from __future__ import annotations

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
    _explanation = (
        'The shared base of the MCP tools and prompts defined in the database: '
        'a name, a description and Python code evaluated in a sandbox.'
    )
    _order = 'sequence, name'
    _code_field = 'code'

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
