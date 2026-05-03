from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    ids_field,
    model_field,
)


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
                'model': model_field(),
                'ids': ids_field('update'),
                'values': {
                    'type': 'object',
                    'description': (
                        'Field values to change. Only include fields you '
                        'want to modify.'
                    ),
                },
                'context': context_field(),
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
                'model': model_field(),
                'ids': ids_field('permanently delete'),
                'context': context_field(),
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
