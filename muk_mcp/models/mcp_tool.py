import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MCPTool(models.Model):

    _name = 'muk_mcp.tool'
    _description = "MCP Tool"
    _order = 'sequence, name'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
    )

    description = fields.Text(
        string="Description",
        required=True,
    )

    input_schema = fields.Text(
        string="Input Schema",
        help="JSON Schema defining the tool parameters.",
    )

    handler = fields.Char(
        string="Handler Method",
        required=True,
        help="Python method name on muk_mcp.tool that implements the tool.",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    read_only = fields.Boolean(
        string="Read Only",
        default=False,
        help="Hint to the AI client that this tool does not modify data.",
    )

    category = fields.Selection(
        selection=[
            ('read', "Read"),
            ('write', "Write"),
            ('execute', "Execute"),
        ],
        string="Category",
        required=True,
        default='read',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_input_schema(self):
        self.ensure_one()
        if not self.input_schema:
            return {
                'type': 'object',
                'properties': {},
            }
        return json.loads(self.input_schema)

    def _notify_tools_changed(self):
        try:
            self.env['muk_mcp.notification'].push_to_all_sessions(
                'notifications/tools/list_changed',
            )
        except Exception:
            pass

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_execute(self, arguments, env):
        self.ensure_one()
        handler_method = getattr(self, self.handler, None)
        if handler_method is None:
            raise UserError(_(
                'Tool handler "%(handler)s" not found.',
                handler=self.handler,
            ))
        return handler_method(arguments, env)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def get_tools(self):
        tools = self.search([('active', '=', True)])
        return [{
            'name': tool.name,
            'description': tool.description,
            'inputSchema': tool._get_input_schema(),
        } for tool in tools]

    def _handle_list_models(self, arguments, env):
        search_term = arguments.get('search', '')
        models_data = []
        for model_name, model_cls in env.items():
            if search_term and search_term.lower() not in model_name.lower():
                continue
            try:
                description = model_cls._description or model_name
            except Exception:
                description = model_name
            models_data.append({
                'model': model_name,
                'description': description,
            })
        models_data.sort(key=lambda m: m['model'])
        limit = arguments.get('limit', 100)
        return json.dumps(models_data[:limit], indent=2)

    def _handle_list_modules(self, arguments, env):
        search_term = arguments.get('search', '')
        state = arguments.get('state', 'installed')
        domain = [('state', '=', state)]
        if search_term:
            domain.append(('name', 'ilike', search_term))
        modules = env['ir.module.module'].sudo().search_read(
            domain,
            fields=['name', 'shortdesc', 'state', 'installed_version'],
            order='name asc',
        )
        return json.dumps([{
            'name': m['name'],
            'label': m['shortdesc'],
            'version': m['installed_version'] or '',
            'state': m['state'],
        } for m in modules], indent=2)

    def _handle_get_model_schema(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        model = env[model_name]
        fields_info = model.fields_get(
            attributes=[
                'string', 'type', 'help', 'required',
                'readonly', 'relation', 'selection',
            ]
        )
        return json.dumps(fields_info, indent=2, default=str)

    def _handle_search_read(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        domain = arguments.get('domain', [])
        fields_list = arguments.get('fields')
        limit = arguments.get('limit', 80)
        offset = arguments.get('offset', 0)
        order = arguments.get('order')
        data = env[model_name].search_read(
            domain,
            fields=fields_list,
            limit=limit,
            offset=offset,
            order=order,
        )
        return json.dumps(data, indent=2, default=str)

    def _handle_read(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        ids = arguments.get('ids', [])
        if isinstance(ids, int):
            ids = [ids]
        fields_list = arguments.get('fields')
        records = env[model_name].browse(ids)
        data = records.read(fields_list)
        return json.dumps(data, indent=2, default=str)

    def _handle_create(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        values = arguments.get('values', {})
        record = env[model_name].create(values)
        return json.dumps({
            'id': record.id,
            'display_name': record.display_name,
        })

    def _handle_write(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        ids = arguments.get('ids', [])
        if isinstance(ids, int):
            ids = [ids]
        if not ids:
            return json.dumps({'error': 'No record IDs provided'})
        values = arguments.get('values', {})
        records = env[model_name].browse(ids)
        records.write(values)
        return json.dumps({
            'success': True,
            'ids': ids,
        })

    def _handle_unlink(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        ids = arguments.get('ids', [])
        if isinstance(ids, int):
            ids = [ids]
        if not ids:
            return json.dumps({'error': 'No record IDs provided'})
        records = env[model_name].browse(ids)
        records.unlink()
        return json.dumps({
            'success': True,
            'deleted_ids': ids,
        })

    def _handle_call(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        method_name = arguments.get('method')
        if not method_name:
            return json.dumps({'error': 'No method name provided'})
        if method_name.startswith('_'):
            return json.dumps({
                'error': f'Private methods cannot be called: {method_name!r}',
            })
        ids = arguments.get('ids', [])
        if isinstance(ids, int):
            ids = [ids]
        args = arguments.get('args', [])
        kwargs = arguments.get('kwargs', {})
        model = env[model_name]
        if ids:
            model = model.browse(ids)
        method = getattr(model, method_name, None)
        if method is None:
            return json.dumps({
                'error': f'Method {method_name!r} not found on {model_name!r}',
            })
        result = method(*args, **kwargs)
        return json.dumps(result, indent=2, default=str)

    def _handle_search_count(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        domain = arguments.get('domain', [])
        count = env[model_name].search_count(domain)
        return json.dumps({'count': count})

    def _handle_get_user_context(self, arguments, env):
        user = env.user
        company = env.company
        return json.dumps({
            'uid': user.id,
            'login': user.login,
            'name': user.name,
            'lang': user.lang,
            'tz': user.tz or '',
            'company_id': company.id,
            'company_name': company.name,
            'currency': company.currency_id.name,
            'country': company.country_id.name or '',
            'groups': [
                g.full_name for g in user.group_ids.sorted('full_name')
            ],
        }, indent=2)

    def _handle_get_record_messages(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        record_id = arguments.get('id')
        if not record_id:
            return json.dumps({'error': 'Record ID is required'})
        limit = arguments.get('limit', 20)
        messages = env['mail.message'].search_read(
            [
                ('model', '=', model_name),
                ('res_id', '=', record_id),
            ],
            fields=[
                'date', 'author_id', 'message_type', 'subtype_id',
                'body', 'tracking_value_ids',
            ],
            limit=limit,
            order='date desc',
        )
        return json.dumps(messages, indent=2, default=str)

    def _handle_post_message(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        record_id = arguments.get('id')
        if not record_id:
            return json.dumps({'error': 'Record ID is required'})
        body = arguments.get('body', '')
        if not body:
            return json.dumps({'error': 'Message body is required'})
        record = env[model_name].browse(record_id)
        msg = record.message_post(
            body=body,
            message_type=arguments.get('type', 'comment'),
            subtype_xmlid=arguments.get('subtype', 'mail.mt_comment'),
        )
        return json.dumps({
            'id': msg.id,
            'date': str(msg.date),
        })

    def _handle_read_group(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        domain = arguments.get('domain', [])
        fields_list = arguments.get('fields', [])
        groupby = arguments.get('groupby', [])
        if not groupby:
            return json.dumps({'error': 'groupby is required'})
        data = env[model_name].read_group(
            domain,
            fields=fields_list,
            groupby=groupby,
            limit=arguments.get('limit'),
            orderby=arguments.get('order', False),
            lazy=arguments.get('lazy', True),
        )
        return json.dumps(data, indent=2, default=str)

    def _handle_get_access_rights(self, arguments, env):
        model_name = arguments.get('model')
        if not model_name or model_name not in env:
            return json.dumps({'error': f'Model {model_name!r} not found'})
        operations = ['read', 'write', 'create', 'unlink']
        rights = {
            op: env[model_name].check_access_rights(op, raise_exception=False)
            for op in operations
        }
        rules = env['ir.model.access'].sudo().search_read(
            [('model_id.model', '=', model_name)],
            fields=['name', 'group_id', 'perm_read', 'perm_write',
                    'perm_create', 'perm_unlink'],
        )
        return json.dumps({
            'model': model_name,
            'current_user_rights': rights,
            'access_rules': rules,
        }, indent=2, default=str)

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._notify_tools_changed()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._notify_tools_changed()
        return result

    def unlink(self):
        result = super().unlink()
        self._notify_tools_changed()
        return result
