from __future__ import annotations

from typing import Any

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.common import coerce_json_value
from odoo.addons.muk_mcp.tools.uri import record_field_uri


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_read(
        self, records: models.BaseModel, fields: list[str]
    ) -> list[dict[str, Any]]:
        """Read ``fields`` of ``records``, binary fields as resource URIs without their content."""
        rows = records.with_context(bin_size=True).read(fields)
        binary = [name for name in fields if records._fields[name].type == 'binary']
        for row in rows:
            for name in binary:
                row[name] = row[name] and record_field_uri(
                    records._name, row['id'], name
                )
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
                coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
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
            "parent_of. Without 'fields' only id and display_name come "
            "back; name the fields you need. Use 'limit' to paginate large "
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
                        "Field names to return. Binary fields come back as a "
                        "resource URI, or false when empty. Example: "
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
        records = self._resolve_model(model).search(
            coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
            limit=limit,
            offset=offset,
            order=order,
        )
        return self._mcp_read(records, fields or ['display_name'])

    @api.model
    @mcp_tool(
        name='read_records',
        description=(
            'Read specific records by their database IDs. Use this when '
            'you already know the exact record IDs (e.g. from a previous '
            'search_read result or from a Many2one field value). Without '
            '"fields" it returns the stored base fields of each record; name '
            'computed, one2many or many2many fields to get them.'
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
                        'Field names to return. Binary fields come back as a '
                        'resource URI, or false when empty.'
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
        self._mcp_assert_records_allowed(model, target_ids)
        records = self._resolve_model(model).browse(target_ids)
        return self._mcp_read(
            records,
            fields
            or [
                name
                for name in records.fields_get(attributes=())
                if (field := records._fields[name]).prefetch is True
                and field.type not in ('one2many', 'many2many')
            ],
        )

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
        groups = target.read_group(
            coerce_json_value(self._mcp_apply_domain(model, domain)) or [],
            list(aggregates),
            list(groupby),
            limit=limit,
            orderby=order or False,
            lazy=False,
        )
        data = []
        for group in groups:
            entry = {}
            for key in groupby:
                base = key.split(':')[0]
                value = group.get(key, group.get(base))
                if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], int):
                    entry[key] = (value[0], value[1])
                else:
                    entry[key] = value
            for agg_spec in aggregates:
                base = agg_spec.split(':')[0]
                entry[agg_spec] = group.get(agg_spec, group.get(base))
            entry['%s_count' % groupby[0].split(':')[0]] = group.get('__count', 0)
            data.append(entry)
        return data
