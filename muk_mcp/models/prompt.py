import contextlib
import inspect
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools.safe_eval import json as safe_json

from odoo.addons.muk_mcp.core.prompt import get_prompt_index
from odoo.addons.muk_mcp.tools.logger import LoggerProxy
from odoo.addons.muk_mcp.tools.protocol import (
    make_prompt_message,
    make_text_content,
)


class MCPPrompt(models.Model):

    _name = 'muk_mcp.prompt'
    _description = "MCP Prompt"
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

    title = fields.Char(
        string="Title",
        required=True,
    )

    description = fields.Text(
        string="Description",
        required=True,
    )

    arguments = fields.Text(
        string="Arguments",
        help=(
            "JSON array of argument definitions: "
            "[{\"name\": ..., \"description\": ..., \"required\": ...}]."
        ),
    )

    body = fields.Text(
        string="Body",
        required=True,
        default=(
            "# Available variables:\n"
            "#   env         - Odoo Environment (with caller context applied)\n"
            "#   arguments   - dict of prompt arguments from the AI client\n"
            "#   json        - json module\n"
            "#   UserError   - odoo.exceptions.UserError\n"
            "#   logger      - logging.Logger for this prompt\n"
            "#\n"
            "# Set 'result' to the prompt text (a string) or a list of\n"
            "# message dicts to return it.\n"
            "result = ''\n"
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _validate_prompt_arguments(self, entry, arguments):
        missing = [
            arg['name'] for arg in entry['arguments']
            if arg.get('required') and arg['name'] not in arguments
        ]
        if missing:
            raise UserError(_(
                "Missing required prompt arguments: %s",
                ', '.join(missing),
            ))

    @api.model
    def _normalize_prompt_messages(self, raw):
        if isinstance(raw, str):
            return [make_prompt_message('user', raw)]
        messages = []
        for item in raw or []:
            if isinstance(item, dict) and 'role' in item:
                content = item.get('content')
                if isinstance(content, str):
                    item = {**item, 'content': make_text_content(content)}
                messages.append(item)
        return messages

    @api.model
    def _complete_prompt_argument(self, prompt_name, arg_name, value):
        if arg_name == 'model':
            records = self.env['ir.model'].sudo().search_read(
                [('model', '=ilike', '%s%%' % (value or ''))],
                fields=['model'],
                limit=101,
                order='model asc',
            )
            return [record['model'] for record in records]
        return []

    @api.model
    def _run_method_prompt(self, entry, arguments):
        mixin = self.env['muk_mcp.mixin']
        func = inspect.unwrap(getattr(type(mixin), entry['method']))
        try:
            return func(mixin, **arguments)
        except TypeError as exc:
            raise UserError(_(
                "Invalid arguments for prompt %(name)s: %(error)s",
                name=entry.get('method'), error=exc,
            ))

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

    def _run(self, arguments, env):
        eval_context = self._get_eval_context(arguments, env)
        safe_eval(self.body.strip(), eval_context, mode="exec")
        return eval_context.get('result')

    def _notify_prompts_changed(self):
        with contextlib.suppress(Exception):
            self.env['muk_mcp.notification'].push_to_all_sessions(
                'notifications/prompts/list_changed',
            )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_prompts(self):
        result = []
        for name, entry in get_prompt_index(self.env).items():
            prompt = {
                'name': name,
                'description': entry['description'],
            }
            if entry.get('title'):
                prompt['title'] = entry['title']
            if entry.get('arguments'):
                prompt['arguments'] = entry['arguments']
            result.append(prompt)
        return result

    @api.model
    def get_prompt(self, name, arguments=None):
        if not (entry := get_prompt_index(self.env).get(name)):
            raise UserError(_("Prompt not found: %s", name))
        arguments = dict(arguments or {})
        self._validate_prompt_arguments(entry, arguments)
        if entry['kind'] == 'db':
            raw = self.sudo().browse(entry['id'])._run(arguments, self.env)
        else:
            raw = self._run_method_prompt(entry, arguments)
        result = {'messages': self._normalize_prompt_messages(raw)}
        if entry.get('description'):
            result['description'] = entry['description']
        return result

    @api.model
    def complete_argument(self, ref, argument):
        ref = ref or {}
        argument = argument or {}
        values = []
        if ref.get('type') == 'ref/prompt' and ref.get('name'):
            values = self._complete_prompt_argument(
                ref['name'],
                argument.get('name'),
                argument.get('value') or '',
            )
        return {
            'completion': {
                'values': values[:100],
                'total': len(values),
                'hasMore': len(values) > 100,
            },
        }

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('body')
    def _check_body(self):
        for record in self.sudo().filtered('body'):
            message = test_python_expr(
                expr=record.body.strip(), mode="exec",
            )
            if message:
                raise ValidationError(message)

    @api.constrains('arguments')
    def _check_arguments(self):
        for record in self.sudo().filtered('arguments'):
            try:
                parsed = json.loads(record.arguments)
            except (TypeError, ValueError) as exc:
                raise ValidationError(_(
                    "Prompt %(name)s has invalid Arguments JSON: %(error)s",
                    name=record.name, error=exc,
                ))
            if not isinstance(parsed, list):
                raise ValidationError(_(
                    "Prompt %(name)s Arguments must be a JSON array.",
                    name=record.name,
                ))

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._notify_prompts_changed()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._notify_prompts_changed()
        return result

    def unlink(self):
        result = super().unlink()
        self._notify_prompts_changed()
        return result
