from __future__ import annotations

import contextlib
import inspect
import json
from typing import Any

from odoo import _, api, fields, models
from odoo.api import Environment
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import json as safe_json
from odoo.tools.safe_eval import safe_eval, test_python_expr

from odoo.addons.muk_mcp.core.prompt import get_prompt_index
from odoo.addons.muk_mcp.tools.logger import LoggerProxy
from odoo.addons.muk_mcp.tools.protocol import (
    make_prompt_message,
    make_text_content,
)


class MCPPrompt(models.Model):
    """Prompt definition exposed to MCP clients and resolved on demand."""

    _name = 'muk_mcp.prompt'
    _description = 'MCP Prompt'
    _order = 'sequence, name'

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

    title = fields.Char(
        string='Title',
        required=True,
    )

    description = fields.Text(
        string='Description',
        required=True,
    )

    arguments = fields.Text(
        string='Arguments',
        help=(
            'JSON array of argument definitions: '
            '[{"name": ..., "description": ..., "required": ...}].'
        ),
    )

    body = fields.Text(
        string='Body',
        required=True,
        default=(
            '# Available variables:\n'
            '#   env         - Odoo Environment (with caller context applied)\n'
            '#   arguments   - dict of prompt arguments from the AI client\n'
            '#   json        - json module\n'
            '#   UserError   - odoo.exceptions.UserError\n'
            '#   logger      - logging.Logger for this prompt\n'
            '#\n'
            '# Set "result" to the prompt text (a string) or a list of\n'
            '# message dicts to return it.\n'
            "result = ''\n"
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _validate_prompt_arguments(
        self,
        entry: dict[str, Any],
        arguments: dict[str, Any],
    ) -> None:
        """Raise if any argument marked required by the entry is absent."""
        missing = [
            arg['name']
            for arg in entry['arguments']
            if arg.get('required') and arg['name'] not in arguments
        ]
        if missing:
            raise UserError(
                _(
                    'Missing required prompt arguments: %s',
                    ', '.join(missing),
                ),
            )

    @api.model
    def _normalize_prompt_messages(self, raw) -> list[dict[str, Any]]:
        """Coerce a string or message list into MCP prompt messages."""
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
    def _complete_prompt_argument(
        self,
        prompt_name: str,
        arg_name: str,
        value: str,
    ) -> list[str]:
        """Return autocompletion candidates for a prompt argument value."""
        if arg_name == 'model':
            records = (
                self.env['ir.model']
                .sudo()
                .search_read(
                    [('model', '=ilike', '%s%%' % (value or ''))],
                    fields=['model'],
                    limit=101,
                    order='model asc',
                )
            )
            return [record['model'] for record in records]
        return []

    @api.model
    def _run_method_prompt(
        self,
        entry: dict[str, Any],
        arguments: dict[str, Any],
    ) -> Any:
        """Invoke a code-defined prompt method on the MCP mixin."""
        mixin = self.env['muk_mcp.mixin']
        func = inspect.unwrap(getattr(type(mixin), entry['method']))
        try:
            return func(mixin, **arguments)
        except TypeError as exc:
            raise UserError(
                _(
                    'Invalid arguments for prompt %(name)s: %(error)s',
                    name=entry.get('method'),
                    error=exc,
                ),
            )

    def _get_eval_context(
        self,
        arguments: dict[str, Any],
        env: Environment,
    ) -> dict[str, Any]:
        """Build the sandbox namespace, applying any caller context override.

        Pops ``context`` from ``arguments`` and folds it into the environment.
        """
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

    def _run(self, arguments: dict[str, Any], env: Environment) -> Any:
        """Evaluate the prompt body in the sandbox and return ``result``."""
        eval_context = self._get_eval_context(arguments, env)
        safe_eval(self.body.strip(), eval_context, mode='exec')
        return eval_context.get('result')

    def _notify_prompts_changed(self) -> None:
        """Invalidate the prompt registry cache so clients see the change."""
        with contextlib.suppress(Exception):
            self.env['muk_mcp.notification'].push_to_all_sessions(
                'notifications/prompts/list_changed',
            )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_prompts(self) -> list[dict[str, Any]]:
        """Return the MCP prompt listing for all available prompts."""
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
    def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a named prompt to its messages for the given arguments.

        :raise UserError: if no prompt with that name exists.
        """
        if not (entry := get_prompt_index(self.env).get(name)):
            raise UserError(_('Prompt not found: %s', name))
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
    def get_playground_prompts(self) -> list[dict[str, Any]]:
        """Return prompt metadata for the playground UI."""
        return [
            {
                'name': name,
                'title': entry.get('title') or '',
                'description': entry['description'],
                'arguments': entry['arguments'],
                'kind': entry['kind'],
            }
            for name, entry in get_prompt_index(self.env).items()
        ]

    @api.model
    def complete_argument(
        self,
        ref: dict[str, Any] | None,
        argument: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return an MCP completion response for a prompt argument."""
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
    def _check_body(self) -> None:
        """Validate that the prompt body is a safe Python expression."""
        for record in self.sudo().filtered('body'):
            message = test_python_expr(
                expr=record.body.strip(),
                mode='exec',
            )
            if message:
                raise ValidationError(message)

    @api.constrains('arguments')
    def _check_arguments(self) -> None:
        """Validate that the arguments field is a JSON array."""
        for record in self.sudo().filtered('arguments'):
            try:
                parsed = json.loads(record.arguments)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    _(
                        'Prompt %(name)s has invalid Arguments JSON: %(error)s',
                        name=record.name,
                        error=exc,
                    ),
                )
            if not isinstance(parsed, list):
                raise ValidationError(
                    _(
                        'Prompt %(name)s Arguments must be a JSON array.',
                        name=record.name,
                    ),
                )

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list: list[dict[str, Any]]) -> MCPPrompt:
        """Create prompts and notify sessions that the listing changed."""
        records = super().create(vals_list)
        self._notify_prompts_changed()
        return records

    def write(self, vals: dict[str, Any]) -> bool:
        """Write prompts and notify sessions that the listing changed."""
        result = super().write(vals)
        self._notify_prompts_changed()
        return result

    def unlink(self) -> bool:
        """Delete prompts and notify sessions that the listing changed."""
        result = super().unlink()
        self._notify_prompts_changed()
        return result
