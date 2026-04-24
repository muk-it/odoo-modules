import base64

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.common import coerce_json_value
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
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'fields': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        "Field paths. Use '/' to traverse relations."
                    ),
                },
                'ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': (
                        "Record ids. Omit to use the domain + limit."
                    ),
                },
                'domain': {
                    'type': 'string',
                    'description': (
                        "JSON-encoded Odoo domain array when 'ids' is "
                        "not supplied. Example: \"[[\\\"state\\\",\\\"=\\\","
                        "\\\"sale\\\"]]\". Pass \"[]\" or omit for no filter."
                    ),
                },
                'format': {
                    'type': 'string',
                    'enum': ['csv', 'xlsx'],
                    'description': "Output format. Default: 'csv'.",
                    'default': 'csv',
                },
                'limit': {
                    'type': 'integer',
                    'description': (
                        "Max records when using domain. Default 1000."
                    ),
                    'default': 1000,
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
            model, ids, coerce_json_value(domain), limit, order,
        )
        exporter = self._build_exporter(format)
        rows = records.export_data(list(fields)).get('datas') or []
        descriptors = [
            {'name': f, 'label': f, 'type': 'char'} for f in fields
        ]
        content = exporter.from_data(descriptors, list(fields), rows)
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
