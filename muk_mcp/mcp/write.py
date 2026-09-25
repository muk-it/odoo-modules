from __future__ import annotations

import base64
from typing import Any

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    ids_field,
    model_field,
)
from odoo.addons.muk_mcp.tools.parser import normalize_ids
from odoo.addons.muk_mcp.tools.url_fetch import fetch_url


class MCPMixin(models.AbstractModel):
    """Add MCP write tools to the shared MCP mixin."""

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
                'model': model_field(),
                'values': {
                    'type': 'object',
                    'description': (
                        'Field values for the new record. Example: '
                        '{"name": "John", "email": "john@example.com", '
                        '"company_id": 1}.'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'values'],
        },
        category='write',
    )
    def _mcp_create_records(
        self,
        model: str,
        values,
    ) -> dict[str, Any]:
        """Create one record from ``values`` and return its id and display name.

        :raise AccessError: when the created record lies outside the
            configured record domain; the savepoint rolls the insert back
            so the forbidden record is never persisted.
        """
        with self.env.cr.savepoint():
            record = self._resolve_model(model).create(values or {})
            self._mcp_assert_records_allowed(model, [record.id])
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
                'model': model_field(),
                'ids': ids_field('update'),
                'values': {
                    'type': 'object',
                    'description': (
                        'Field values to change. Only include fields you want to modify.'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'ids', 'values'],
        },
        category='write',
    )
    def _mcp_update_records(
        self,
        model: str,
        ids,
        values,
    ) -> dict[str, Any]:
        """Write ``values`` to the records named by ``ids`` and return the affected ids.

        :raise UserError: when ``ids`` resolves to an empty list.
        """
        target_ids = normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._mcp_assert_records_allowed(model, target_ids)
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
                'model': model_field(),
                'ids': ids_field('permanently delete'),
                'context': context_field(),
            },
            'required': ['model', 'ids'],
        },
        category='write',
    )
    def _mcp_delete_records(self, model: str, ids) -> dict[str, Any]:
        """Unlink the records named by ``ids`` and return the deleted ids.

        :raise UserError: when ``ids`` resolves to an empty list.
        """
        target_ids = normalize_ids(ids)
        if not target_ids:
            raise UserError(_('No record IDs provided'))
        self._mcp_assert_records_allowed(model, target_ids)
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
                'model': model_field(),
                'id': {
                    'type': 'integer',
                    'description': 'ID of the record to update.',
                },
                'field': {
                    'type': 'string',
                    'description': (
                        'Name of the binary or image field to set (e.g. image_1920).'
                    ),
                },
                'url': {
                    'type': 'string',
                    'description': (
                        'Public https:// URL of the file (max. 20 MB). '
                        'Private and internal addresses are rejected.'
                    ),
                },
                'context': context_field(),
            },
            'required': ['model', 'id', 'field', 'url'],
        },
        category='write',
    )
    def _mcp_set_binary_from_url(
        self,
        model: str,
        id: int,
        field: str,
        url: str,
    ) -> dict[str, Any]:
        """Download ``url`` into the binary ``field`` of one record and describe it.

        :raise UserError: when ``field`` is not a binary field, the record does
            not exist, the download is refused or fails, or an image field
            receives content that is not an image.
        """
        target = self._resolve_model(model)
        definition = target._fields.get(field)
        if definition is None or definition.type != 'binary':
            raise UserError(
                _(
                    'Field %(field)r is not a binary field on %(model)s.',
                    field=field,
                    model=model,
                ),
            )
        if not (record := target.browse(id).exists()):
            raise UserError(
                _('%(model)s(%(id)s) does not exist.', model=model, id=id),
            )
        self._mcp_assert_records_allowed(model, [record.id])
        body, mimetype = fetch_url(url)
        sniffed = guess_mimetype(body)
        if isinstance(definition, fields.Image) and not sniffed.startswith('image/'):
            raise UserError(
                _(
                    'The file at %(url)s is not an image (%(mimetype)s).',
                    url=url,
                    mimetype=sniffed,
                ),
            )
        record.write({field: base64.b64encode(body)})
        return {
            'success': True,
            'id': record.id,
            'field': field,
            'size': len(body),
            'mimetype': mimetype or sniffed,
        }
