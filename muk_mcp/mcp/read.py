from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.common import coerce_json_value


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

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
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'domain': {
                    'type': 'string',
                    'description': (
                        'JSON-encoded Odoo domain array, e.g. '
                        '"[[\\"is_company\\",\\"=\\",true]]". Pass "[]" or '
                        'omit for no filter.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': (
                            "Optional Odoo context overrides. Example: "
                            "{'active_test': false} to count archived records too."
                    ),
                },
            },
            'required': ['model'],
        },
        category='read',
    )
    def _mcp_search_count(self, model, domain=None):
        return {
            'count': self._resolve_model(model).search_count(
                coerce_json_value(domain) or [],
            ),
        }

    @api.model
    @mcp_tool(
        name='search_read',
        description=(
            "Search for records matching a domain filter and return their "
            "field values. The domain is a list of conditions using Odoo's "
            "domain syntax: each condition is [field, operator, value]. "
            "Conditions are AND-ed by default. Use '|' for OR. Operators: "
            "=, !=, >, >=, <, <=, like, ilike, in, not in, child_of, "
            "parent_of. Always specify 'fields' to avoid returning all "
            "fields (which can be slow). Use 'limit' to paginate large "
            "result sets."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': (
                        "Technical model name (e.g. 'res.partner')."
                    ),
                },
                'domain': {
                    'type': 'string',
                    'description': (
                        "JSON-encoded Odoo domain array. Examples: "
                        "\"[[\\\"is_company\\\",\\\"=\\\",true]]\", "
                        "\"[\\\"|\\\",[\\\"email\\\",\\\"ilike\\\",\\\"@gmail\\\"],"
                        "[\\\"email\\\",\\\"ilike\\\",\\\"@outlook\\\"]]\", "
                        "\"[[\\\"state\\\",\\\"=\\\",\\\"sale\\\"],"
                        "[\\\"date_order\\\",\\\">=\\\",\\\"2024-01-01\\\"]]\". "
                        "Pass \"[]\" or omit for no filter."
                    ),
                },
                'fields': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        "Field names to return. ALWAYS specify this to "
                        "avoid returning all fields. Example: "
                        "['name','email','phone','state']."
                    ),
                },
                'limit': {
                    'type': 'integer',
                    'description': (
                        'Maximum records to return. Use small values (10-50) '
                        'for exploration, larger (up to 500) when you need '
                        'bulk data.'
                    ),
                    'default': 80,
                },
                'offset': {
                    'type': 'integer',
                    'description': 'Number of records to skip for pagination.',
                    'default': 0,
                },
                'order': {
                    'type': 'string',
                    'description': (
                        "Sort order. Example: 'create_date desc', "
                        "'name asc, id desc'."
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': (
                        "Optional Odoo context overrides. Example: "
                        "{'active_test': false} to include archived records, "
                        "{'lang': 'de_DE'} to change language."
                    ),
                },
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
        return self._resolve_model(model).search_read(
            coerce_json_value(domain) or [],
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
        )

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
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Record IDs to read.',
                },
                'fields': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Field names to return. ALWAYS specify this.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': (
                        "Optional Odoo context overrides. Example: "
                        "{'active_test': false} to include archived records."
                    ),
                },
            },
            'required': ['model', 'ids'],
        },
        category='read',
    )
    def _mcp_read_records(self, model, ids, fields=None):
        target_ids = self._normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        return self._resolve_model(model).browse(target_ids).read(fields)

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
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'domain': {
                    'type': 'string',
                    'description': (
                        'JSON-encoded Odoo domain array. Same syntax as '
                        'search_read. Pass "[]" or omit for no filter.'
                    ),
                },
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
                'context': {
                    'type': 'object',
                    'description': (
                        "Optional Odoo context overrides. Example: "
                        "{'active_test': false} to include archived records "
                        "in aggregation."
                    ),
                },
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
            coerce_json_value(domain) or [],
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
