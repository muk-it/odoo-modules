from __future__ import annotations

import base64
from typing import Any

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.uri import attachment_uri, parse_uri


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

    def _resolve_model(self, model):
        if not model or model not in self.env:
            raise UserError(_("Model %r not found", model))
        return self.env[model]

    @api.model
    def _mcp_record(self, model: str, res_id: int | None) -> models.BaseModel:
        """Return the existing record a tool targets.

        :raise UserError: when the model is unknown, the id is missing or the
            record does not exist.
        """
        target = self._resolve_model(model)
        if not res_id:
            raise UserError(_("A record ID is required with a model."))
        if not (record := target.browse(res_id).exists()):
            raise UserError(_(
                "Record %(model)s/%(id)s not found", model=model, id=res_id,
            ))
        return record

    @api.model
    def _mcp_file_result(
        self, filename: str, mimetype: str, content: bytes, delivery: str
    ) -> dict[str, Any]:
        """Return a produced file as base64, or stored with a one-time download link.

        Links go only to clients calling over the MCP endpoint; callers inside
        Odoo get the file inline and keep it themselves.
        """
        result = {'filename': filename, 'mimetype': mimetype}
        if delivery != 'link' or not (request and getattr(request, '_mcp_key', None)):
            return {**result, 'content_base64': base64.b64encode(content).decode()}
        attachment = self.env['ir.attachment'].create(
            {'name': filename, 'raw': content}
        )
        uri = attachment_uri(attachment.id)
        _transfer, url = self.env['muk_mcp.transfer']._issue(
            'download', uri=uri, attachment_id=attachment.id
        )
        return {**result, 'file': uri, 'download_url': url}

    @api.model
    def _resolve_resource_target(self, uri: str) -> tuple[models.BaseModel, str]:
        """Return the record and binary field an ``odoo://`` URI names, checked for reading.

        :raise UserError: if the URI is unsupported, the field not binary or the
            record missing.
        :raise AccessError: without read access on the record or the field.
        """
        kind, params = parse_uri(uri) or (None, {})
        if kind == 'attachment':
            record = self.env['ir.attachment'].browse(params['attachment_id'])
            field = 'raw'
        elif kind == 'record_field':
            target = self._resolve_model(params['model'])
            field = params['field']
            if (
                target._fields.get(field) is None or
                target._fields[field].type != 'binary'
            ):
                raise UserError(_(
                    "Field %(f)r is not a readable binary field on %(m)s.",
                    f=field, m=target._name,
                ))
            record = target.browse(params['record_id'])
        else:
            raise UserError(_("Unsupported resource URI: %r", uri))
        if not record.exists():
            raise UserError(_("Resource %s does not exist.", uri))
        if record._name == 'ir.attachment':
            record.check('read')
        else:
            record.check_access_rights('read')
            record.check_access_rule('read')
            record.check_field_access_rights('read', [field])
        return record, field

    @api.model
    def _resolve_resource_uri(self, uri: str) -> tuple[str, bytes, str]:
        """Load the file an ``odoo://`` URI names as ``(mimetype, raw, name)``.

        :raise UserError: as ``_resolve_resource_target``, or when a record's
            binary field is empty.
        """
        record, field = self._resolve_resource_target(uri)
        if record._name == 'ir.attachment':
            return record.mimetype or '', record.raw or b'', record.name or ''
        attachment = self.env['ir.attachment'].sudo().search(
            [
                ('res_model', '=', record._name),
                ('res_id', '=', record.id),
                ('res_field', '=', field),
            ],
            limit=1
        )
        if attachment:
            raw, mimetype, name = (
                attachment.raw or b'',
                attachment.mimetype,
                attachment.name or field,
            )
        else:
            if not (value := record.with_context(bin_size=False)[field]):
                raise UserError(_("Resource %s is empty.", uri))
            if isinstance(value, str):
                value = value.encode('ascii')
            try:
                raw = base64.b64decode(value)
            except (ValueError, TypeError):
                raw = value
            mimetype, name = None, field
        return mimetype or guess_mimetype(raw), raw, name

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
