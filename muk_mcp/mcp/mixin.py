import base64
import json

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.uri import parse_uri


class MCPMixin(models.AbstractModel):

    _name = 'muk_mcp.mixin'
    _description = 'MCP Tool Mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _normalize_ids(ids):
        if ids is None:
            return []
        if isinstance(ids, int):
            return [ids]
        return list(ids)

    @staticmethod
    def _coerce_json_value(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (TypeError, ValueError):
                return value
        return value

    def _resolve_model(self, model):
        if not model or model not in self.env:
            raise UserError(_("Model %r not found", model))
        return self.env[model]

    @api.model
    def _resolve_resource_uri(self, uri):
        handlers = {
            'attachment': self._resolve_resource_attachment,
            'record_field': self._resolve_resource_record_field,
        }
        if not (parsed := parse_uri(uri)) or parsed[0] not in handlers:
            raise UserError(_("Unsupported resource URI: %r", uri))
        return handlers[parsed[0]](**parsed[1])

    @api.model
    def _resolve_resource_attachment(self, attachment_id):
        attachment = self.env['ir.attachment'].browse(attachment_id)
        if not attachment.exists():
            raise UserError(_(
                "Attachment %(aid)s does not exist.", aid=attachment_id,
            ))
        attachment.check('read')
        return (
            attachment.mimetype or '',
            attachment.raw or b'',
            attachment.name or ''
        )

    @api.model
    def _resolve_resource_record_field(self, model, record_id, field):
        target = self._resolve_model(model)
        if (
            target._fields.get(field) is None or
            target._fields[field].type != 'binary'
        ):
            raise UserError(_(
                "Field %(f)r is not a readable binary field on %(m)s.",
                f=field, m=model,
            ))
        if (
            not (record := target.browse(record_id)) or
            not record.exists()
        ):
            raise UserError(_(
                "%(m)s(%(id)s) does not exist.", m=model, id=record_id,
            ))
        record.check_access_rights('read', raise_exception=True)
        record.check_access_rule('read')
        attachment = self.env['ir.attachment'].sudo().search(
            [
                ('res_model', '=', model),
                ('res_id', '=', record_id),
                ('res_field', '=', field),
            ],
            limit=1
        )
        if attachment:
            raw = attachment.raw or b''
            mimetype, name = (
                attachment.mimetype,
                attachment.name or field
            )
        else:
            value = record.with_context(bin_size=False)[field]
            if not value:
                raise UserError(_(
                    "Field %(f)s is empty on %(m)s(%(id)s).",
                    f=field, m=model, id=record_id,
                ))
            if isinstance(value, str):
                value = value.encode('ascii')
            try:
                raw = base64.b64decode(value)
            except (ValueError, TypeError):
                raw = value
            mimetype, name = None, field
        return (mimetype or guess_mimetype(raw), raw, name)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='list_modules',
        description=(
            "List installed Odoo modules with their names, versions, and "
            "descriptions. Use 'search' to filter. This helps understand "
            "which apps and features are active in the system (e.g. is "
            "'sale' installed? is 'stock' installed?)."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'search': {
                    'type': 'string',
                    'description': 'Filter module names by substring.',
                },
                'state': {
                    'type': 'string',
                    'description': "Filter by state. Default: 'installed'.",
                    'enum': [
                        'installed', 'uninstalled',
                        'to upgrade', 'to install',
                    ],
                    'default': 'installed',
                },
            },
        },
        category='read',
    )
    def _mcp_list_modules(self, search='', state='installed'):
        domain = [('state', '=', state)]
        if search:
            domain.append(('name', 'ilike', search))
        modules = self.env['ir.module.module'].sudo().search_read(
            domain,
            fields=['name', 'shortdesc', 'state', 'installed_version'],
            order='name asc',
        )
        return [
            {
                'name': m['name'],
                'label': m['shortdesc'],
                'version': m['installed_version'] or '',
                'state': m['state'],
            }
            for m in modules
        ]
