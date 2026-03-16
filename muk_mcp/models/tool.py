import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools.safe_eval import json as safe_json

class MCPTool(models.Model):

    _name = 'muk_mcp.tool'
    _description = "MCP Tool"
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
    )

    description = fields.Text(
        string="Description",
        required=True,
    )

    input_schema = fields.Text(
        string="Input Schema",
        help="JSON Schema defining the tool parameters.",
    )

    code = fields.Text(
        string="Python Code",
        required=True,
        default=(
            "# Available variables:\n"
            "#   env         - Odoo Environment (with caller context applied)\n"
            "#   arguments   - dict of tool arguments from the AI client\n"
            "#   json        - json module\n"
            "#   UserError   - odoo.exceptions.UserError\n"
            "#   logger      - logging.Logger for this tool\n"
            "#\n"
            "# Set 'result' to a JSON-serializable value to return it.\n"
            "result = {}\n"
        ),
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    category = fields.Selection(
        selection=[
            ('read', "Read"),
            ('write', "Write"),
        ],
        string="Category",
        required=True,
        default='read',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_input_schema(self):
        return json.loads(self.input_schema) if self.input_schema else {
            'type': 'object',
            'properties': {},
        }

    def _get_eval_context(self, arguments, env):
        context = arguments.pop('context', None)
        if context and isinstance(context, dict):
            env = env(context={**env.context, **context})
        return {
            'env': env,
            'arguments': arguments,
            'json': safe_json,
            'getattr': getattr,
            'hasattr': hasattr,
            'UserError': UserError,
            'logger': logging.getLogger(
                f'{__name__} ({self.name})'
            ),
        }

    def _notify_tools_changed(self):
        try:
            self.env['muk_mcp.notification'].push_to_all_sessions(
                'notifications/tools/list_changed',
            )
        except Exception:
            pass

    def _run(self, arguments, env):
        eval_context = self._get_eval_context(arguments, env)
        safe_eval(self.code.strip(), eval_context, mode="exec")
        result = eval_context.get('result')
        return result if isinstance(result, str) else json.dumps(
            result, indent=2, default=str,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self):
        return [
            {
                'name': tool.name,
                'description': tool.description,
                'inputSchema': tool._get_input_schema(),
            }
            for tool in self.search([('active', '=', True)])
        ]

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('code')
    def _check_code(self):
        for record in self.sudo().filtered('code'):
            message = test_python_expr(
                expr=record.code.strip(), mode="exec",
            )
            if message:
                raise ValidationError(message)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._notify_tools_changed()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._notify_tools_changed()
        return result

    def unlink(self):
        result = super().unlink()
        self._notify_tools_changed()
        return result
