import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.url_fetch import fetch_url


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='create_records',
        description=(
            'Create a new record. Pass field values as a JSON object. For '
            'Many2one fields, pass the integer ID. For Many2many fields, '
            'use command tuples: [[6,0,[id1,id2]]] to set, [[4,id]] to '
            'add. For One2many fields, use [[0,0,{values}]] to create '
            'inline records. Check required fields with describe_model '
            'first.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'values': {
                    'type': 'object',
                    'description': (
                        "Field values for the new record. Example: "
                        "{'name': 'John', 'email': 'john@example.com', "
                        "'company_id': 1}."
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': (
                        "Optional Odoo context overrides. Example: "
                        "{'default_type': 'contact'} to set default field values."
                    ),
                },
            },
            'required': ['model', 'values'],
        },
        category='write',
    )
    def _mcp_create_records(self, model, values):
        record = self._resolve_model(model).create(values or {})
        return {
            'id': record.id,
            'display_name': record.display_name,
        }

    @api.model
    @mcp_tool(
        name='update_records',
        description=(
            'Update existing records by their IDs. Only pass the fields '
            'you want to change — other fields remain untouched. Same '
            'value formats as create_records apply for relational fields.'
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
                    'description': 'Record IDs to update.',
                },
                'values': {
                    'type': 'object',
                    'description': (
                        'Field values to change. Only include fields you '
                        'want to modify.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['model', 'ids', 'values'],
        },
        category='write',
    )
    def _mcp_update_records(self, model, ids, values):
        target_ids = self._normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._resolve_model(model).browse(target_ids).write(values or {})
        return {'success': True, 'ids': target_ids}

    @api.model
    @mcp_tool(
        name='delete_records',
        description=(
            'Permanently delete records by their IDs. This cannot be '
            'undone. Some records cannot be deleted if other records '
            'depend on them (e.g. you cannot delete a partner that has '
            'invoices). Consider archiving (setting active=false) instead '
            'of deleting.'
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
                    'description': 'Record IDs to permanently delete.',
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['model', 'ids'],
        },
        category='write',
    )
    def _mcp_delete_records(self, model, ids):
        target_ids = self._normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._resolve_model(model).browse(target_ids).unlink()
        return {'success': True, 'deleted_ids': target_ids}

    @api.model
    @mcp_tool(
        name='set_binary_from_url',
        description=(
            'Use this to set an image or file field (e.g. image_1920 of a '
            'product) from a public https URL. Odoo downloads the file '
            'itself. NEVER pass base64 file content in tool arguments. For '
            'files the user uploaded or that only exist in the sandbox, '
            'first create a file_storage share link on the platform and '
            'pass that share URL.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'id': {
                    'type': 'integer',
                    'description': 'ID of the record to update.',
                },
                'field': {
                    'type': 'string',
                    'description': (
                        'Name of the binary or image field to set '
                        '(e.g. image_1920).'
                    ),
                },
                'url': {
                    'type': 'string',
                    'description': (
                        'Public https:// URL of the file (max. 20 MB). '
                        'Private and internal addresses are rejected.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['model', 'id', 'field', 'url'],
        },
        category='write',
    )
    def _mcp_set_binary_from_url(self, model, id, field, url):
        target = self._resolve_model(model)
        definition = target._fields.get(field)
        if definition is None or definition.type != 'binary':
            raise UserError(_(
                'Field %(field)r is not a binary field on %(model)s.',
                field=field, model=model
            ))
        record = target.browse(id).exists()
        if not record:
            raise UserError(_(
                '%(model)s(%(id)s) does not exist.', model=model, id=id
            ))
        body, mimetype = fetch_url(url)
        sniffed = guess_mimetype(body)
        if isinstance(definition, fields.Image) and not sniffed.startswith('image/'):
            raise UserError(_(
                'The file at %(url)s is not an image (%(mimetype)s).',
                url=url, mimetype=sniffed
            ))
        record.write({field: base64.b64encode(body)})
        return {
            'success': True,
            'id': record.id,
            'field': field,
            'size': len(body),
            'mimetype': mimetype or sniffed,
        }
