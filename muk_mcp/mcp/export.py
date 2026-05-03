import base64

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    domain_field,
    fields_field,
    ids_field,
    model_field,
)
from odoo.addons.web.controllers.export import CSVExport, ExcelExport


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _resolve_records(
        self,
        model,
        ids,
        domain,
        limit,
        order,
    ):
        target = self._resolve_model(model)
        target_ids = self._normalize_ids(ids)
        if target_ids:
            return target.browse(target_ids).exists()
        return target.search(
            domain or [], limit=limit or None, order=order or None,
        )

    @api.model
    def _build_exporter(self, format):
        return ExcelExport() if format == 'xlsx' else CSVExport()

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='export_records',
        description=(
            "Export records as CSV or XLSX, returned as base64. "
            "Field paths use '/' to traverse relations, e.g. "
            "'partner_id/name' or 'order_line/product_id/default_code'. "
            "Honours record rules and field access."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'fields': fields_field(
                    required_hint=False,
                    extra_note="Use '/' to traverse relations.",
                    example=['name', 'partner_id/name', 'order_line/product_id/default_code'],
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
                    'description': "Output format.",
                },
                'limit': {
                    'type': 'integer',
                    'default': 1000,
                    'description': 'Maximum records when using domain.',
                },
                'order': {
                    'type': 'string',
                    'description': "Sort order.",
                },
            },
            'required': ['model', 'fields'],
        },
        category='read',
    )
    def _mcp_export_records(
        self,
        model,
        fields,
        ids=None,
        domain=None,
        format='csv',
        limit=1000,
        order=None,
    ):
        if not fields:
            raise UserError(_('No fields provided'))
        records = self._resolve_records(
            model, ids, self._coerce_json_value(domain), limit, order,
        )
        exporter = self._build_exporter(format)
        rows = records.export_data(list(fields)).get('datas') or []
        # 17's web.export.CSVExport/ExcelExport.from_data only takes
        # ``(fields, rows)``. 18+ added a leading ``descriptors`` argument
        # for header metadata.
        content = exporter.from_data(list(fields), rows)
        if isinstance(content, str):
            content = content.encode('utf-8-sig')
        return {
            'filename': '%s%s' % (
                model.replace('.', '_'), exporter.extension,
            ),
            'mimetype': exporter.content_type,
            'row_count': len(rows),
            'content_base64': base64.b64encode(content).decode(),
        }
