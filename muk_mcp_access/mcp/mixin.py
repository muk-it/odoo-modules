from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.osv import expression

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
        """Combine the caller domain with the model's configured record domain."""
        extra = self._mcp_record_domain(model)
        if extra is None:
            return domain
        base = coerce_json_value(domain) or []
        return expression.AND([base, extra])

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
                expression.AND([[('id', 'in', ids)], extra]),
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

        Merges the domain into the method's ``domain`` argument so queries
        such as ``search_read`` cannot reach outside it, and asserts the
        records the call returns stay inside it.

        :raise AccessError: when the call returns records outside the
            configured domain.
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
