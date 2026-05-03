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
from odoo.addons.muk_mcp.tools.uri import record_field_uri


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _swap_binary_to_uri(self, model, rows):
        target = self.env[model]
        binary_fields = [
            name for name, field in target._fields.items()
            if field.type == 'binary'
        ]
        if not binary_fields:
            return rows
        for row in rows:
            rid = row.get('id')
            if not rid:
                continue
            for fname in binary_fields:
                if fname in row and row[fname]:
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
    def _mcp_search_count(self, model, domain=None):
        return {
            'count': self._resolve_model(model).search_count(
                self._coerce_json_value(domain) or [],
            ),
        }

    @api.model
    @mcp_tool(
        name='search_read',
        description=(
            "Search for records matching a domain filter and return their "
            "field values. Always specify 'fields' to avoid returning all "
            "fields (which can be slow). Use 'limit' to paginate large "
            "result sets."
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
                        "Sort order, e.g. 'create_date desc', "
                        "'name asc, id desc'."
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
        model,
        domain=None,
        fields=None,
        limit=80,
        offset=0,
        order=None,
    ):
        rows = self._resolve_model(model).search_read(
            self._coerce_json_value(domain) or [],
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
    def _mcp_read_records(self, model, ids, fields=None):
        target_ids = self._normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        rows = self._resolve_model(model).browse(target_ids).read(fields)
        return self._swap_binary_to_uri(model, rows)

    @api.model
    @mcp_tool(
        name='read_group',
        description=(
            'Perform grouped aggregation on records — the equivalent of '
            'SQL GROUP BY. Groups records matching a domain by one or '
            'more fields and returns aggregate values (count, sum, avg). '
            'Use this for statistics and dashboards: e.g. count invoices '
            'by state, sum sale amounts by month, average order value by '
            'salesperson.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'domain': domain_field(),
                'fields': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        "Fields to aggregate. Include the groupby field and "
                        "any numeric fields to sum/avg. Example: "
                        "['state', 'amount_total']."
                    ),
                },
                'groupby': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        "Fields to group by. Examples: ['state'], "
                        "['partner_id', 'state'], ['date_order:month']."
                    ),
                },
                'limit': {
                    'type': 'integer',
                    'description': 'Maximum number of groups to return.',
                },
                'order': {
                    'type': 'string',
                    'description': (
                        "Sort order for groups. Example: 'amount_total desc'."
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'fields', 'groupby'],
        },
        category='read',
    )
    def _mcp_read_group(
        self,
        model,
        fields,
        groupby,
        domain=None,
        limit=None,
        order=None,
    ):
        if not groupby:
            raise UserError(_('groupby is required'))
        target = self._resolve_model(model)
        aggregates = []
        numeric_types = {'integer', 'float', 'monetary'}
        for field_spec in (fields or []):
            if ':' in field_spec:
                aggregates.append(field_spec)
                continue
            if field_spec in groupby:
                continue
            field = target._fields.get(field_spec)
            if field is not None and field.type in numeric_types:
                aggregates.append('%s:sum' % field_spec)
            else:
                aggregates.append('%s:count_distinct' % field_spec)
        if '__count' not in aggregates:
            aggregates.append('__count')
        rows = target._read_group(
            self._coerce_json_value(domain) or [],
            groupby=groupby,
            aggregates=aggregates,
            limit=limit,
            order=order or None,
        )
        keys = list(groupby) + list(aggregates)
        data = []
        for row in rows:
            entry = {}
            for key, value in zip(keys, row):
                if hasattr(value, '_name') and hasattr(value, 'ids'):
                    if len(value) == 1:
                        entry[key] = (value.id, value.display_name)
                    else:
                        entry[key] = [(r.id, r.display_name) for r in value]
                else:
                    entry[key] = value
            if '__count' in entry:
                entry['%s_count' % groupby[0]] = entry.pop('__count')
            data.append(entry)
        return data
