from __future__ import annotations

from typing import Any

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.service.model import get_public_method

from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids


class MCPMixin(models.AbstractModel):
    """Wrap the MCP read and write tools to enforce the configured record domains."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_records(
        self,
        model: str,
        ids,
        domain: list | None,
        limit: int | None,
        order: str | None,
    ) -> models.BaseModel:
        """Assert id access or merge the record domain before resolving records."""
        if normalize_ids(ids):
            self._mcp_assert_records_allowed(model, ids)
            return super()._resolve_records(model, ids, domain, limit, order)
        return super()._resolve_records(
            model,
            ids,
            self._mcp_apply_domain(model, domain),
            limit,
            order,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def _mcp_call_method(
        self,
        model: str,
        method: str,
        ids=None,
        args: str | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Assert record access before invoking a method on specific records."""
        target = self._resolve_model(model)
        try:
            unbound = get_public_method(target, method)
        except (AccessError, AttributeError) as exc:
            raise UserError(str(exc))
        if not getattr(unbound, '_api_model', False):
            target_ids = normalize_ids(ids)
            if not target_ids and (positional := coerce_json_value(args) or []):
                target_ids = normalize_ids(positional[0])
            if target_ids:
                self._mcp_assert_records_allowed(model, target_ids)
        return super()._mcp_call_method(
            model,
            method,
            ids=ids,
            args=args,
            kwargs=kwargs,
        )

    @api.model
    def _mcp_search_count(self, model: str, domain=None) -> dict[str, Any]:
        """Count records after merging in the model's configured record domain."""
        return super()._mcp_search_count(
            model,
            domain=self._mcp_apply_domain(model, domain),
        )

    @api.model
    def _mcp_search_read(
        self,
        model: str,
        domain=None,
        fields: list[str] | None = None,
        limit: int = 80,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search records after merging in the model's configured record domain."""
        return super()._mcp_search_read(
            model,
            domain=self._mcp_apply_domain(model, domain),
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )

    @api.model
    def _mcp_read_group(
        self,
        model: str,
        groupby: list[str],
        aggregates: list[str] | None = None,
        domain=None,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group records after merging in the model's configured record domain."""
        return super()._mcp_read_group(
            model,
            groupby,
            aggregates=aggregates,
            domain=self._mcp_apply_domain(model, domain),
            limit=limit,
            order=order,
        )

    @api.model
    def _mcp_read_records(
        self, model: str, ids, fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Assert record access before reading records by id."""
        self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_read_records(model, ids, fields=fields)

    @api.model
    def _mcp_create_records(self, model: str, values) -> dict[str, Any]:
        """Create a record and assert it stays within the configured record domain.

        :raise AccessError: when the created record lies outside the
            configured domain; the savepoint rolls the insert back so the
            forbidden record is never persisted.
        """
        with self.env.cr.savepoint():
            result = super()._mcp_create_records(model, values)
            self._mcp_assert_records_allowed(model, [result['id']])
        return result

    @api.model
    def _mcp_update_records(self, model: str, ids, values) -> dict[str, Any]:
        """Assert record access before updating records by id."""
        self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_update_records(model, ids, values)

    @api.model
    def _mcp_delete_records(self, model: str, ids) -> dict[str, Any]:
        """Assert record access before deleting records by id."""
        self._mcp_assert_records_allowed(model, ids)
        return super()._mcp_delete_records(model, ids)
