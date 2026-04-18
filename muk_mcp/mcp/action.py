from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.models import BaseModel
from odoo.service.model import get_public_method

from ..core.tool import mcp_tool


EXECUTE_METHOD_MAX_RECORDS = 200


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='execute_method',
        description=(
            "Call a public method on an Odoo model or recordset. Use this "
            "for business logic actions like confirming a sale order "
            "(model='sale.order', method='action_confirm', ids=[42]) or "
            "posting an invoice (model='account.move', "
            "method='action_post', ids=[10]). Common methods: "
            "action_confirm (sales/purchases), action_post (invoices), "
            "action_done (pickings), action_assign (pickings), "
            "action_cancel (most documents). Private methods (starting "
            "with '_') are blocked for safety."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'method': {
                    'type': 'string',
                    'description': (
                        "Public method name (e.g. 'action_confirm', "
                        "'action_post', 'message_post')."
                    ),
                },
                'ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': (
                        'Record IDs to call the method on. Omit for '
                        '@api.model methods.'
                    ),
                },
                'args': {
                    'type': 'array',
                    'description': (
                        'Positional arguments to pass to the method.'
                    ),
                },
                'kwargs': {
                    'type': 'object',
                    'description': (
                        'Keyword arguments to pass to the method.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['model', 'method'],
        },
        category='write',
    )
    def execute_method(
        self, model, method, ids=None, args=None, kwargs=None,
    ):
        target = self._resolve_model(model)
        try:
            unbound = get_public_method(target, method)
        except AccessError as exc:
            raise UserError(str(exc))
        except AttributeError as exc:
            raise UserError(str(exc))
        target_ids = self._normalize_ids(ids)
        if getattr(unbound, '_api_model', False):
            recordset = target
        else:
            recordset = target.browse(target_ids) if target_ids else target
        result = unbound(recordset, *(args or []), **(kwargs or {}))
        if isinstance(result, BaseModel) and len(result) > EXECUTE_METHOD_MAX_RECORDS:
            return {
                'truncated': True,
                'model': result._name,
                'count': len(result),
                'limit': EXECUTE_METHOD_MAX_RECORDS,
                'ids': result[:EXECUTE_METHOD_MAX_RECORDS].ids,
            }
        return result
