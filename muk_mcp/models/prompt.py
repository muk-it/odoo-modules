from __future__ import annotations

import inspect
import json
from typing import Any

from odoo import api, fields, models
from odoo.api import Environment
from odoo.exceptions import UserError, ValidationError

from odoo.addons.muk_mcp.core.prompt import get_prompt_index
from odoo.addons.muk_mcp.tools.protocol import make_text_content


class MCPPrompt(models.Model):
    """Prompt definition exposed to MCP clients and resolved on demand."""

    _name = 'muk_mcp.prompt'
    _inherit = 'muk_mcp.sandbox'
    _description = 'MCP Prompt'
    _explanation = (
        'A prompt template an MCP client lists and fills in, defined in the '
        'database with arguments and a Python body that renders the messages.'
    )
    _code_field = 'body'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    title = fields.Char(
        string='Title',
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
                self.env._(
                    'Missing required prompt arguments: %s',
                    ', '.join(missing),
                ),
            )

    @api.model
    def _normalize_prompt_messages(self, raw) -> list[dict[str, Any]]:
        """Coerce a string or message list into MCP prompt messages."""
        if isinstance(raw, str):
            return [{'role': 'user', 'content': make_text_content(raw)}]
        messages = []
        for item in raw or []:
            if isinstance(item, dict) and 'role' in item:
                content = item.get('content')
                if isinstance(content, str):
                    item = {**item, 'content': make_text_content(content)}
                messages.append(item)
        return messages

    @api.model
    def _run_method_prompt(
        self,
        entry: dict[str, Any],
        arguments: dict[str, Any],
        env: Environment,
    ) -> Any:
        """Invoke a code-defined prompt method on the MCP mixin.

        :raise UserError: when the arguments do not fit the method.
        """
        mixin = env[entry['model']]
        func = inspect.unwrap(getattr(type(mixin), entry['method']))
        try:
            inspect.signature(func).bind(mixin, **arguments)
        except TypeError as exc:
            raise UserError(
                self.env._(
                    'Invalid arguments for prompt %(name)s: %(error)s',
                    name=entry['name'],
                    error=exc,
                ),
            ) from exc
        return func(mixin, **arguments)

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
            raise UserError(self.env._('Prompt not found: %s', name))
        arguments = dict(arguments or {})
        self._validate_prompt_arguments(entry, arguments)
        env = self.env
        if isinstance(context := arguments.pop('context', None), dict):
            env = env(context={**env.context, **context})
        if entry['kind'] == 'db':
            raw = self.sudo().browse(entry['id'])._run(arguments, env)
        else:
            raw = self._run_method_prompt(entry, arguments, env)
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
        """Return an MCP completion response, suggesting model names for ``model``."""
        ref, argument = ref or {}, argument or {}
        values = []
        if (
            ref.get('type') == 'ref/prompt'
            and ref.get('name')
            and argument.get('name') == 'model'
        ):
            records = (
                self.env['ir.model']
                .sudo()
                .search_read(
                    [('model', '=ilike', '%s%%' % (argument.get('value') or ''))],
                    fields=['model'],
                    limit=101,
                    order='model asc',
                )
            )
            values = [record['model'] for record in records]
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

    @api.constrains('arguments')
    def _check_arguments(self) -> None:
        """Validate that the arguments field is a JSON array."""
        for record in self.sudo().filtered('arguments'):
            try:
                parsed = json.loads(record.arguments)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    self.env._(
                        'Prompt %(name)s has invalid Arguments JSON: %(error)s',
                        name=record.name,
                        error=exc,
                    ),
                ) from exc
            if not isinstance(parsed, list):
                raise ValidationError(
                    self.env._(
                        'Prompt %(name)s Arguments must be a JSON array.',
                        name=record.name,
                    ),
                )
