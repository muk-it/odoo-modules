from __future__ import annotations

from typing import Any

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    domain_field,
    fields_field,
    ids_field,
    model_field,
)
from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids
from odoo.addons.muk_mcp.tools.uri import record_field_uri


class MCPMixin(models.AbstractModel):
    """Add MCP read tools to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _swap_binary_to_uri(
        self,
        model: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Replace populated binary field values in ``rows`` with ``odoo://`` resource URIs in place."""
        target = self.env[model]
        binary_fields = [
            name for name, field in target._fields.items() if field.type == 'binary'
        ]
        if not binary_fields:
            return rows
        for row in rows:
            rid = row.get('id')
            if not rid:
                continue
            for fname in binary_fields:
                if row.get(fname):
                    row[fname] = record_field_uri(model, rid, fname)
        return rows

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='search_count',
        description=(
            'Count the number of records matching a domain filter without '
            'returning the data. Use this to check how many records exist '
            'before doing a full search_read, or to get statistics (e.g. '
            'how many open invoices, how many active customers).'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'domain': domain_field(),
                'context': context_field(),
            },
            'required': ['model'],
        },
        category='read',
    )
    def _mcp_search_count(
        self,
        model: str,
        domain=None,
    ) -> dict[str, Any]:
        """Count records matching ``domain`` and return them under a ``count`` key."""
        return {
            'count': self._resolve_model(model).search_count(
                coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
            ),
        }

    @api.model
    @mcp_tool(
        name='search_read',
        description=(
            'Search for records matching a domain filter and return their '
            'field values. Always specify "fields" to avoid returning all '
            'fields (which can be slow). Use "limit" to paginate large '
            'result sets.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'domain': domain_field(),
                'fields': fields_field(),
                'limit': {
                    'type': 'integer',
                    'default': 80,
                    'description': (
                        'Maximum records to return. Use small values (10-50) '
                        'for exploration, larger (up to 500) for bulk data.'
                    ),
                },
                'offset': {
                    'type': 'integer',
                    'default': 0,
                    'description': 'Records to skip for pagination.',
                },
                'order': {
                    'type': 'string',
                    'description': (
                        'Sort order, e.g. "create_date desc", "name asc, id desc".'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model'],
        },
        category='read',
    )
    def _mcp_search_read(
        self,
        model: str,
        domain=None,
        fields: list[str] | None = None,
        limit: int = 80,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search records by ``domain`` and return their field values with binaries swapped to URIs."""
        rows = self._resolve_model(model).search_read(
            coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )
        return self._swap_binary_to_uri(model, rows)

    @api.model
    @mcp_tool(
        name='read_records',
        description=(
            'Read specific records by their database IDs. Use this when '
            'you already know the exact record IDs (e.g. from a previous '
            'search_read result or from a Many2one field value). Returns '
            'all requested fields for each ID.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'ids': ids_field('read'),
                'fields': fields_field(),
                'context': context_field(),
            },
            'required': ['model', 'ids'],
        },
        category='read',
    )
    def _mcp_read_records(
        self,
        model: str,
        ids,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records by their database IDs with binaries swapped to URIs.

        :raise UserError: when ``ids`` resolves to an empty list.
        """
        target_ids = normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._mcp_assert_records_allowed(model, target_ids)
        rows = self._resolve_model(model).browse(target_ids).read(fields)
        return self._swap_binary_to_uri(model, rows)

    @api.model
    @mcp_tool(
        name='read_group',
        description=(
            'Perform grouped aggregation on records — the equivalent of '
            'SQL GROUP BY. Groups records matching a domain by one or '
            'more fields and returns aggregate values. Use this for '
            'statistics and dashboards: e.g. count invoices by state, '
            'sum sale amounts by month, average order value by '
            'salesperson.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'domain': domain_field(),
                'groupby': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Fields to group by. Examples: '
                        '["state"], ["partner_id", "state"], '
                        '["date_order:month"] (granularity suffixes: '
                        ':year, :quarter, :month, :week, :day, :hour).'
                    ),
                },
                'aggregates': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Aggregate specs as "<field>:<agg>". Aggregations: '
                        'sum, avg, min, max, count, count_distinct, '
                        'array_agg, bool_or, bool_and. Examples: '
                        '["amount_total:sum"], '
                        '["partner_id:count_distinct", "amount_total:avg"]. '
                        '"__count" is always included.'
                    ),
                },
                'limit': {
                    'type': 'integer',
                    'description': 'Maximum number of groups to return.',
                },
                'order': {
                    'type': 'string',
                    'description': (
                        'Sort order for groups, e.g. "amount_total:sum desc".'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'groupby'],
        },
        category='read',
    )
    def _mcp_read_group(
        self,
        model: str,
        groupby: list[str],
        aggregates: list[str] | None = None,
        domain=None,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Group records by one or more fields and return aggregate values, always including ``__count``.

        :raise UserError: when ``groupby`` is empty.
        """
        if not groupby:
            raise UserError(_('groupby is required'))
        aggregates = list(aggregates or [])
        if '__count' not in aggregates:
            aggregates.append('__count')
        return self._resolve_model(model).formatted_read_group(
            coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
            groupby=groupby,
            aggregates=aggregates,
            limit=limit,
            order=order or None,
        )
