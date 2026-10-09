from __future__ import annotations

from typing import Any

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    delivery_field,
    domain_field,
    fields_field,
    ids_field,
    model_field,
)
from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids
from odoo.addons.muk_mcp.tools.xlsx import XlsxExport
from odoo.addons.web.controllers.export import CSVExport


class MCPMixin(models.AbstractModel):
    """Add the ``export_records`` MCP tool for CSV/XLSX data export."""

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
        """Return the records to export, preferring explicit ``ids``.

        When ``ids`` are given they are browsed and filtered through
        :meth:`exists`; otherwise the ``domain`` is searched with ``limit`` and
        ``order``.
        """
        target = self._resolve_model(model)
        target_ids = normalize_ids(ids)
        if target_ids:
            self._mcp_assert_records_allowed(model, target_ids)
            return target.browse(target_ids).exists()
        return target.search(
            self._mcp_apply_domain(model, domain) or [],
            limit=limit or None,
            order=order or None,
        )

    @api.model
    def _build_exporter(self, format: str) -> XlsxExport | CSVExport:
        """Return the export handler for the requested format (xlsx or csv)."""
        return XlsxExport() if format == 'xlsx' else CSVExport()

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='export_records',
        description=(
            'Export records as CSV or XLSX. '
            'Field paths use "/" to traverse relations, e.g. '
            '"partner_id/name" or "order_line/product_id/default_code". '
            'Honours record rules and field access.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'fields': fields_field(
                    extra_note="Use '/' to traverse relations.",
                    example=[
                        'name',
                        'partner_id/name',
                        'order_line/product_id/default_code',
                    ],
                ),
                'ids': ids_field(
                    'export',
                    extra_note='Omit to use the domain + limit.',
                ),
                'domain': domain_field(
                    extra_note="Used when 'ids' is not supplied.",
                ),
                'format': {
                    'type': 'string',
                    'enum': ['csv', 'xlsx'],
                    'default': 'csv',
                    'description': 'Output format.',
                },
                'limit': {
                    'type': 'integer',
                    'default': 1000,
                    'description': 'Maximum records when using domain.',
                },
                'order': {
                    'type': 'string',
                    'description': 'Sort order.',
                },
                'delivery': delivery_field(),
                'context': context_field(),
            },
            'required': ['model', 'fields'],
        },
        category='read',
    )
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
        """Export the selected records and return the encoded file payload.

        Resolves records from ``ids`` or ``domain``, runs them through the
        web export controller for the requested ``format``, and returns the
        file with its row count.

        :raise UserError: if no ``fields`` are provided.
        """
        if not fields:
            raise UserError(_('No fields provided'))
        records = self._resolve_records(
            model,
            ids,
            coerce_json_value(domain),
            limit,
            order,
        )
        exporter = self._build_exporter(format)
        rows = records.export_data(list(fields)).get('datas') or []
        descriptors = [{'name': f, 'label': f, 'type': 'char'} for f in fields]
        content = exporter.from_data(descriptors, list(fields), rows)
        if isinstance(content, str):
            content = content.encode('utf-8-sig')
        filename = model.replace('.', '_') + exporter.extension
        return {
            **self._mcp_file_result(filename, exporter.content_type, content, delivery),
            'row_count': len(rows),
        }
