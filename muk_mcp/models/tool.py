import contextlib
import inspect
import json
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools.safe_eval import json as safe_json
from odoo.tools import config
from odoo.http import request

from odoo.addons.muk_mcp.core.tool import get_tool_index

from odoo.addons.muk_mcp.tools.encoder import encode_request, encode_response, RecordEncoder
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied
from odoo.addons.muk_mcp.tools.logger import LoggerProxy
from odoo.addons.muk_mcp.tools.protocol import ToolContent

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

    registry = fields.Selection(
        selection=[
            ('mcp', "MCP"),
        ],
        string="Registry",
        help="Restrict the tool to a single surface.",
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
        if isinstance(result, ToolContent):
            return result
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
        status, text, info, error = 'ok', None, {}, None
        arguments = dict(arguments or {})
        model_name = arguments.get('model')
        start = time.monotonic()
        try:
            text, info, model_name = self._execute(
                name, arguments, env, enforce_scope,
            )
            return text, info
        except Exception as exc:
            status = (
                'denied'
                if isinstance(exc, MCPScopeDenied)
                else 'error'
            )
            error = str(exc)
            raise
        finally:
            if config.get('mcp_logging', True):
                self.env['muk_mcp.log'].log(**self._tool_log_values(
                    name=name,
                    env=env,
                    request_data=encode_request(arguments),
                    model_name=model_name,
                    status=status,
                    text=text,
                    info=info,
                    error=error,
                    duration_ms=int((time.monotonic() - start) * 1000),
                ))

    @api.model
    def _execute(self, name, arguments, env, enforce_scope):
        if not (entry := get_tool_index(env).get(name)):
            raise UserError(_("Tool not found: %s", name))
        self._check_scope(entry['category'], enforce_scope)
        if isinstance(context_override := arguments.pop('context', None), dict):
            env = env(context={**env.context, **context_override})
        if entry['kind'] == 'db':
            text = self.sudo().browse(entry['id'])._run(arguments, env)
            raw_result = None
        else:
            func = inspect.unwrap(
                getattr(type(env[entry['model']]), entry['method'])
            )
            try:
                raw_result = func(env[entry['model']], **arguments)
            except TypeError as exc:
                raise UserError(_(
                    "Invalid arguments for tool %(name)s: %(error)s",
                    name=name, error=exc,
                ))
            text = self._serialize_result(raw_result)
        return (
            text,
            self._extract_record_info(arguments, raw_result),
            arguments.get('model') or entry.get('model')
        )

    @api.model
    def _tool_log_values(
        self,
        *,
        name,
        env,
        request_data,
        model_name,
        status,
        text,
        info,
        error,
        duration_ms,
    ):
        values = {
            'method': 'tools/call',
            'tool_name': name,
            'user_id': env.uid,
            'model_name': model_name,
            'status': status,
            'duration_ms': duration_ms,
            'request_data': request_data,
        }
        if status == 'ok':
            values['response_data'] = encode_response(text)
            values['res_id'] = info.get('res_id')
            values['res_ids'] = info.get('res_ids')
        else:
            values['error_message'] = error
            values['response_data'] = error
        with contextlib.suppress(Exception):
            if key := getattr(request, '_mcp_key', None):
                values['key_id'] = key.id
            values['ip_address'] = (
                request.httprequest.remote_addr
                if request else None
            )
        return values

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
        with contextlib.suppress(Exception):
            self.env['muk_mcp.notification'].push_to_all_sessions(
                'notifications/tools/list_changed',
            )

    def _run(self, arguments, env):
        eval_context = self._get_eval_context(arguments, env)
        safe_eval(self.code.strip(), eval_context, mode="exec", nocopy=True)
        return self._serialize_result(eval_context.get('result'))

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self, registry=None):
        return [
            {
                'name': name,
                'description': entry['description'],
                'inputSchema': entry['input_schema'],
            }
            for name, entry in get_tool_index(self.env, registry=registry).items()
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
                'registry': entry.get('registry') or None,
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
