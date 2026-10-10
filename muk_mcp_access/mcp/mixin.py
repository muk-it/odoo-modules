from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids


class MCPMixin(models.AbstractModel):
    """Enforce the access allowlist and record domains on MCP operations."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_model(self, model: str) -> models.BaseModel:
        """Resolve a model after asserting it is reachable for the current tool category.

        :raise AccessError: when the model is not exposed via MCP for the
            tool category carried in the context.
        """
        result = super()._resolve_model(model)
        category = self.env.context.get('mcp_tool_category') or 'read'
        if not self.env['muk_mcp_access.model']._is_model_allowed(
            model,
            category,
        ):
            raise AccessError(
                _(
                    'Model %(model)r is not accessible via MCP.',
                    model=model,
                )
            )
        return result

    @api.model
    def _mcp_record_domain(self, model: str) -> list | None:
        """Return the configured record domain for a model, or ``None`` when unrestricted."""
        return self.env['muk_mcp_access.model']._get_model_domain(model)

    @api.model
    def _mcp_apply_domain(self, model: str, domain) -> list:
        """Combine the caller domain with the model's configured record domain.

        :raise AccessError: when a field path of the domain passes through a
            model that is not readable via MCP.
        """
        for leaf in coerce_json_value(domain) or []:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                path = str(leaf[0]).split('.')
                self._mcp_assert_path_allowed(
                    model, [*path, ''] if leaf[1] in ('any', 'not any') else path
                )
        extra = self._mcp_record_domain(model)
        if extra is None:
            return domain
        base = coerce_json_value(domain) or []
        return list(Domain(base) & Domain(extra))

    @api.model
    def _mcp_assert_records_allowed(self, model: str, ids) -> None:
        """Assert every id falls within the model's configured record domain.

        :raise AccessError: when any record lies outside the configured domain.
        """
        extra = self._mcp_record_domain(model)
        ids = normalize_ids(ids)
        if extra is None or not ids:
            return
        allowed = set(
            self.env[model]
            .with_context(active_test=False)
            .search(
                Domain('id', 'in', ids) & Domain(extra),
            )
            .ids
        )
        forbidden = [rid for rid in ids if rid not in allowed]
        if forbidden:
            raise AccessError(
                _(
                    'Records %(ids)s of %(model)r are not accessible via MCP.',
                    ids=forbidden,
                    model=model,
                )
            )

    @api.model
    def _mcp_merge_method_domain(
        self,
        model: str,
        unbound: Callable,
        args: list,
        kwargs: dict,
    ) -> tuple[list, dict]:
        """Merge the model's record domain into the ``domain`` argument of a method.

        Returns the arguments unchanged for a method that takes no domain.
        """
        signature = inspect.signature(unbound)
        parameter = signature.parameters.get('domain')
        if parameter is None:
            return args, kwargs
        index = list(signature.parameters).index('domain') - 1
        if parameter.kind is parameter.POSITIONAL_OR_KEYWORD and index < len(args):
            args = list(args)
            args[index] = self._mcp_apply_domain(model, args[index])
            return args, kwargs
        kwargs = dict(kwargs)
        kwargs['domain'] = self._mcp_apply_domain(model, kwargs.get('domain') or [])
        return args, kwargs

    @api.model
    def _mcp_call_model_method(
        self,
        target: models.BaseModel,
        method: str,
        unbound: Callable,
        args: list,
        kwargs: dict,
    ) -> Any:
        """Restrict an ``@api.model`` call to the model's configured record domain.

        Merges the domain into the ``domain`` argument and raises
        ``AccessError`` when the call returns records outside it.
        """
        model = target._name
        if self._mcp_record_domain(model) is None:
            return super()._mcp_call_model_method(
                target,
                method,
                unbound,
                args,
                kwargs,
            )
        args, kwargs = self._mcp_merge_method_domain(model, unbound, args, kwargs)
        result = super()._mcp_call_model_method(target, method, unbound, args, kwargs)
        if isinstance(result, models.BaseModel) and result._name == model:
            self._mcp_assert_records_allowed(model, result.ids)
        return result

    @api.model
    def _resolve_resource_target(self, uri: str) -> tuple[models.BaseModel, str]:
        """Assert the record behind a resource, or behind an attachment, is exposed via MCP."""
        record, field = super()._resolve_resource_target(uri)
        if record._name != 'ir.attachment':
            self._mcp_assert_records_allowed(record._name, record.ids)
            return record, field
        model, res_id = record.sudo().res_model, record.sudo().res_id
        if model and model not in self._mcp_attachment_exempt_models():
            self._resolve_model(model)
            if res_id:
                self._mcp_assert_records_allowed(model, [res_id])
        return record, field

    @api.model
    def _mcp_assert_path_allowed(self, model: str, path: list[str]) -> None:
        """Assert every model a field path passes through is readable via MCP.

        :raise AccessError: when a related model on the path is not exposed.
        """
        target = self._resolve_model(model)
        for name in path[:-1]:
            field = target._fields.get(name)
            if not field or not field.relational:
                return
            target = self.with_context(mcp_tool_category='read')._resolve_model(
                field.comodel_name
            )

    @api.model
    def _mcp_assert_commands_allowed(self, model: str, values: dict) -> None:
        """Assert the x2many commands in ``values`` only change exposed models.

        :raise AccessError: when a command creates, updates or deletes records
            of a model that is not writable via MCP.
        """
        fields = self._resolve_model(model)._fields
        for name, commands in (values or {}).items():
            field = fields.get(name)
            if not field or field.type not in ('one2many', 'many2many'):
                continue
            for command in commands if isinstance(commands, list) else []:
                if isinstance(command, (list, tuple)) and command[:1] in (
                    [0],
                    [1],
                    [2],
                ):
                    self._resolve_model(field.comodel_name)
                    if len(command) > 2 and isinstance(command[2], dict):
                        self._mcp_assert_commands_allowed(
                            field.comodel_name, command[2]
                        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mcp_export_records(
        self,
        model: str,
        fields: list[str],
        ids=None,
        domain: str | None = None,
        format: str = 'csv',
        limit: int = 1000,
        order: str | None = None,
        delivery: str = 'inline',
    ) -> dict[str, Any]:
        """Refuse an export whose field paths pass through an unexposed model."""
        for path in fields or []:
            self._mcp_assert_path_allowed(model, path.split('/'))
        return super()._mcp_export_records(
            model,
            fields,
            ids=ids,
            domain=domain,
            format=format,
            limit=limit,
            order=order,
            delivery=delivery,
        )

    @api.model
    def _mcp_create_records(self, model: str, values: dict[str, Any]) -> dict[str, Any]:
        """Refuse x2many commands that write to an unexposed model."""
        if isinstance(values, dict):
            self._mcp_assert_commands_allowed(model, values)
        return super()._mcp_create_records(model, values)

    @api.model
    def _mcp_update_records(self, model: str, ids, values) -> dict[str, Any]:
        """Refuse x2many commands that write to an unexposed model."""
        if isinstance(values, dict):
            self._mcp_assert_commands_allowed(model, values)
        return super()._mcp_update_records(model, ids, values)

    @api.model
    def _mcp_call_method(
        self,
        model: str,
        method: str,
        ids=None,
        args: str | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Refuse x2many commands in the arguments that write to an unexposed model."""
        keyword = coerce_json_value(kwargs) or {}
        for value in [*(coerce_json_value(args) or []), *keyword.values()]:
            for values in value if isinstance(value, list) else [value]:
                if isinstance(values, dict):
                    self._mcp_assert_commands_allowed(model, values)
        return super()._mcp_call_method(
            model, method, ids=ids, args=args, kwargs=kwargs
        )
