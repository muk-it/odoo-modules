from odoo import api, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    ids_field,
    model_field,
)


# 17 has no `odoo.service.model.get_public_method` (introduced in 18). Inline an
# equivalent here so MCPMixin can refuse private/unsafe method calls.
_UNSAFE_ATTRIBUTES = (
    'mro',
    '__class__',
    '__init__',
    '__new__',
    '__del__',
    '__setattr__',
    '__getattribute__',
    '__delattr__',
    '__dir__',
    '__hash__',
    '__reduce__',
    '__reduce_ex__',
    '__subclasshook__',
)


def get_public_method(model, name):
    """ Get the public unbound method from a model.

    When the method does not exist or is inaccessible, raise appropriate
    errors. Accessible methods are public (not prefixed with ``_``) and not
    decorated with ``@api.private``.
    """
    assert isinstance(model, models.BaseModel), \
        f"{model!r} is not a BaseModel for {name}"
    cls = type(model)
    method = getattr(cls, name, None)
    if not callable(method):
        raise AttributeError(
            f"The method '{model._name}.{name}' does not exist"
        )
    if (
        name.startswith('_')
        or getattr(method, '_api_private', False)
        or name in _UNSAFE_ATTRIBUTES
    ):
        raise AccessError(
            "Private methods (such as "
            f"'{model._name}.{name}') cannot be called remotely."
        )
    return method


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='call_method',
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
                'model': model_field(),
                'method': {
                    'type': 'string',
                    'description': (
                        "Public method name (e.g. 'action_confirm', "
                        "'action_post', 'message_post')."
                    ),
                },
                'ids': ids_field(
                    'call the method on',
                    extra_note='Omit for @api.model methods.',
                ),
                'args': {
                    'type': 'string',
                    'description': (
                        'JSON-encoded array of positional arguments. '
                        'Example: "[42, true]". Pass "[]" or omit if none.'
                    ),
                },
                'kwargs': {
                    'type': 'object',
                    'description': 'Keyword arguments to pass to the method.',
                },
                'context': context_field(),
            },
            'required': ['model', 'method'],
        },
        category='write',
    )
    def _mcp_call_method(
        self,
        model,
        method,
        ids=None,
        args=None,
        kwargs=None,
    ):
        target = self._resolve_model(model)
        try:
            unbound = get_public_method(target, method)
        except (AccessError, AttributeError) as exc:
            raise UserError(str(exc))
        target_ids = self._normalize_ids(ids)
        if getattr(unbound, '_api_model', False):
            recordset = target
        else:
            recordset = (
                target.browse(target_ids)
                if target_ids else target
            )
        positional = self._coerce_json_value(args) or []
        keyword = self._coerce_json_value(kwargs) or {}
        return unbound(recordset, *positional, **keyword)
