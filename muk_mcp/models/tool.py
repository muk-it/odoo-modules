import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools.safe_eval import json as safe_json

from odoo.addons.muk_mcp.core.tool import get_tool_index
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied
from odoo.addons.muk_mcp.tools.logger import LoggerProxy
from odoo.addons.muk_web_utils.tools.encoder import RecordEncoder

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

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _serialize_result(self, result):
        if not isinstance(result, str):
            return json.dumps(
                result, indent=2, cls=RecordEncoder
            )
        return result

    @api.model
    def _check_scope(self, category, enforce_scope):
        if enforce_scope == 'read' and category != 'read':
            raise MCPScopeDenied(_('Access denied: key scope is read-only'))

    @api.model
    def _call(self, name, arguments, env, enforce_scope=None):
        arguments = dict(arguments or {})
        entry = get_tool_index(env).get(name)
        if not entry:
            raise UserError(_("Tool not found: %s") % name)
        self._check_scope(entry['category'], enforce_scope)
        context_override = arguments.pop('context', None)
        if isinstance(context_override, dict):
            env = env(context={**env.context, **context_override})
        if entry['kind'] == 'db':
            text = self.sudo().browse(entry['id'])._run(arguments, env)
            raw_result = None
        else:
            method = getattr(env[entry['model']], entry['method'])
            try:
                raw_result = method(**arguments)
            except TypeError as exc:
                raise UserError(_(
                    "Invalid arguments for tool %(name)s: %(error)s",
                    name=name, error=exc,
                ))
            text = self._serialize_result(raw_result)
        return text, self._extract_record_info(arguments, raw_result)

    @api.model
    def _extract_record_info(self, arguments, result):
        info = {}
        ids = arguments.get('ids')
        if isinstance(ids, int):
            ids = [ids]
        single_id = arguments.get('id')
        if isinstance(single_id, int):
            ids = [single_id]
        if ids:
            info['res_ids'] = list(ids)
            if len(info['res_ids']) == 1:
                info['res_id'] = info['res_ids'][0]
            return info
        if isinstance(result, dict) and isinstance(result.get('id'), int):
            info['res_id'] = result['id']
            info['res_ids'] = [result['id']]
        return info

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
            'callable': callable,
            'getattr': getattr,
            'hasattr': hasattr,
            'UserError': UserError,
            'logger': LoggerProxy(f'{__name__} ({self.name})'),
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
        return self._serialize_result(eval_context.get('result'))

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self):
        return [
            {
                'name': name,
                'description': entry['description'],
                'inputSchema': entry['input_schema'],
            }
            for name, entry in get_tool_index(self.env).items()
        ]

    @api.model
    def get_playground_tools(self):
        return [
            {
                'name': name,
                'description': entry['description'],
                'inputSchema': entry['input_schema'],
                'category': entry['category'],
                'kind': entry['kind'],
            }
            for name, entry in get_tool_index(self.env).items()
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

    @api.constrains('input_schema')
    def _check_input_schema(self):
        for record in self.sudo().filtered('input_schema'):
            try:
                json.loads(record.input_schema)
            except (TypeError, ValueError) as exc:
                raise ValidationError(_(
                    "Tool %(name)s has invalid Input Schema JSON: %(error)s",
                    name=record.name, error=exc,
                ))

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
