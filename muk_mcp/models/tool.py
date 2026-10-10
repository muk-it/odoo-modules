from __future__ import annotations

import inspect
import json
import time
from typing import Any

from odoo import api, fields, models
from odoo.api import Environment
from odoo.exceptions import AccessError, ConcurrencyError, UserError, ValidationError
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import config

from odoo.addons.muk_mcp.core.tool import get_tool_index
from odoo.addons.muk_mcp.tools.encoder import encode_log
from odoo.addons.muk_mcp.tools.exception import MCPScopeDenied
from odoo.addons.muk_mcp.tools.protocol import (
    ToolContent,
    ToolResult,
    format_internal_error,
    make_text_content,
    make_tool_result,
)
from odoo.addons.muk_web_utils.tools.encoder import RecordEncoder


class MCPTool(models.Model):
    """Tool definition exposed to MCP clients and executed on demand."""

    _name = 'muk_mcp.tool'
    _inherit = 'muk_mcp.sandbox'
    _description = 'MCP Tool'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    category = fields.Selection(
        selection=[
            ('read', 'Read'),
            ('write', 'Write'),
        ],
        string='Category',
        required=True,
        default='read',
    )

    registry = fields.Selection(
        selection=[
            ('mcp', 'MCP'),
        ],
        string='Registry',
        help='Restrict the tool to a single surface.',
    )

    input_schema = fields.Text(
        string='Input Schema',
        help='JSON Schema defining the tool parameters.',
    )

    code = fields.Text(
        string='Python Code',
        required=True,
        default=(
            '# Available variables:\n'
            '#   env         - Odoo Environment (with caller context applied)\n'
            '#   arguments   - dict of tool arguments from the AI client\n'
            '#   json        - json module\n'
            '#   UserError   - odoo.exceptions.UserError\n'
            '#   logger      - logging.Logger for this tool\n'
            '#\n'
            '# Set "result" to a JSON-serializable value to return it.\n'
            'result = {}\n'
        ),
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _serialize_result(self, result) -> Any:
        """Pass protocol objects through; JSON-encode other non-string results."""
        if isinstance(result, (ToolContent, ToolResult)):
            return result
        if not isinstance(result, str):
            return json.dumps(
                result,
                indent=2,
                cls=RecordEncoder,
            )
        return result

    @api.model
    def _check_scope(self, category: str, enforce_scope: str | None) -> None:
        """Raise if a write tool is invoked under a read-only scope."""
        if enforce_scope == 'read' and category != 'read':
            raise MCPScopeDenied(
                self.env._(
                    'Access denied: this tool changes data, but the access is read-only'
                )
            )

    @api.model
    def _coerce_arguments(self, arguments) -> dict[str, Any]:
        """Return a mutable copy of the tool arguments, rejecting non-object payloads.

        :raise UserError: if ``arguments`` is neither ``None`` nor a JSON object.
        """
        if arguments is not None and not isinstance(arguments, dict):
            raise UserError(
                self.env._(
                    'Tool arguments must be a JSON object, got %(kind)s',
                    kind=type(arguments).__name__,
                ),
            )
        return dict(arguments or {})

    @api.model
    def _call_result(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> dict[str, Any]:
        """Run a tool and return its ``tools/call`` result.

        Scope, access, user and unexpected errors become error results.
        Concurrency failures propagate, so the request as a whole is retried.
        """
        try:
            result, _info = self._call(name, arguments, env, enforce_scope)
        except (*PG_CONCURRENCY_EXCEPTIONS_TO_RETRY, ConcurrencyError):
            raise
        except (MCPScopeDenied, AccessError, UserError) as exc:
            return make_tool_result([make_text_content(str(exc))], is_error=True)
        except Exception as exc:
            return make_tool_result(
                [make_text_content(format_internal_error(exc))], is_error=True
            )
        if isinstance(result, ToolResult):
            return dict(result)
        if isinstance(result, ToolContent):
            return make_tool_result(result)
        return make_tool_result([make_text_content(result)])

    @api.model
    def _call(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        env: Environment,
        enforce_scope: str | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Execute a tool in a savepoint, logging the outcome and any error.

        :return: the tool's text result and the extracted record info.
        :raise UserError: if ``arguments`` is neither ``None`` nor a JSON object.
        """
        status, text, info, error, model_name = 'ok', None, {}, None, None
        start = time.monotonic()
        try:
            arguments = self._coerce_arguments(arguments)
            model_name = arguments.get('model')
            with env.cr.savepoint():
                text, info, model_name = self._execute(
                    name, arguments, env, enforce_scope
                )
            return text, info
        except Exception as exc:
            status = 'denied' if isinstance(exc, MCPScopeDenied) else 'error'
            error = str(exc)
            raise
        finally:
            if config.get('mcp_logging', True):
                self.env['muk_mcp.log'].log(
                    **self._tool_log_values(
                        name=name,
                        env=env,
                        arguments=arguments,
                        model_name=model_name,
                        status=status,
                        text=text,
                        info=info,
                        error=error,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    ),
                )

    @api.model
    def _execute(
        self,
        name: str,
        arguments: dict[str, Any],
        env: Environment,
        enforce_scope: str | None,
    ) -> tuple[Any, dict[str, Any], str | None]:
        """Resolve, scope-check and run a tool (DB code or model method).

        :return: serialized text, extracted record info, and target model.
        :raise UserError: if the tool is unknown or called with bad arguments.
        """
        if not (entry := get_tool_index(env).get(name)):
            raise UserError(self.env._('Tool not found: %s', name))
        self._check_scope(entry['category'], enforce_scope)
        if isinstance(context_override := arguments.pop('context', None), dict):
            env = env(context={**env.context, **context_override})
        if entry['kind'] == 'db':
            result = self.sudo().browse(entry['id'])._run(arguments, env)
        else:
            target = env[entry['model']]
            func = inspect.unwrap(getattr(type(target), entry['method']))
            try:
                inspect.signature(func).bind(target, **arguments)
            except TypeError as exc:
                raise UserError(
                    self.env._(
                        'Invalid arguments for tool %(name)s: %(error)s. '
                        'Expected input schema: %(schema)s',
                        name=name,
                        error=exc,
                        schema=json.dumps(entry['input_schema']),
                    ),
                ) from exc
            result = func(target, **arguments)
        return (
            self._serialize_result(result),
            self._extract_record_info(arguments, result),
            arguments.get('model') or entry.get('model'),
        )

    @api.model
    def _tool_log_values(
        self,
        *,
        name: str,
        env: Environment,
        arguments: Any,
        model_name: str | None,
        status: str,
        text: Any,
        info: dict[str, Any],
        error: str | None,
        duration_ms: int,
    ) -> dict[str, Any]:
        """Build the audit-log values of a tool call."""
        values = {
            'method': 'tools/call',
            'tool_name': name,
            'user_id': env.uid,
            'model_name': model_name,
            'status': status,
            'duration_ms': duration_ms,
            'request_data': encode_log(arguments),
        }
        if status == 'ok':
            values['response_data'] = encode_log(text)
            values['res_id'] = info.get('res_id')
            values['res_ids'] = info.get('res_ids')
        else:
            values['error_message'] = error
            values['response_data'] = error
        return values

    @api.model
    def _extract_record_info(
        self,
        arguments: dict[str, Any],
        result,
    ) -> dict[str, Any]:
        """Derive affected record ids from the arguments or the result dict."""
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

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self, registry: str | None = None) -> list[dict[str, Any]]:
        """Return the MCP tool listing, optionally filtered by registry."""
        result = []
        for name, entry in get_tool_index(self.env, registry=registry).items():
            tool = {
                'name': name,
                'description': entry['description'],
                'inputSchema': entry['input_schema'],
                'annotations': {'readOnlyHint': entry['category'] == 'read'},
            }
            if entry['meta']:
                tool['_meta'] = entry['meta']
            result.append(tool)
        return result

    @api.model
    def get_playground_tools(self) -> list[dict[str, Any]]:
        """Return tool metadata for the playground UI."""
        return [
            {
                'name': name,
                'description': entry['description'],
                'inputSchema': entry['input_schema'],
                'category': entry['category'],
                'kind': entry['kind'],
                'registry': entry['registry'],
            }
            for name, entry in get_tool_index(self.env).items()
        ]

    # ----------------------------------------------------------
    # Constraints
    # ----------------------------------------------------------

    @api.constrains('input_schema')
    def _check_input_schema(self) -> None:
        """Validate that the input schema is valid JSON."""
        for record in self.sudo().filtered('input_schema'):
            try:
                json.loads(record.input_schema)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    self.env._(
                        'Tool %(name)s has invalid Input Schema JSON: %(error)s',
                        name=record.name,
                        error=exc,
                    ),
                ) from exc
