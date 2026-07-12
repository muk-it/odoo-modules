from __future__ import annotations

from typing import Any

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.service.model import get_public_method

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.descriptions import (
    context_field,
    ids_field,
    model_field,
)
from odoo.addons.muk_mcp.tools.parser import coerce_json_value, normalize_ids


class MCPMixin(models.AbstractModel):
    """Add the ``call_method`` MCP tool for invoking model business logic."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='call_method',
        description=(
            'Call a public method on an Odoo model or recordset. Use this '
            'for business logic actions like confirming a sale order '
            '(model="sale.order", method="action_confirm", ids=[42]) or '
            'posting an invoice (model="account.move", '
            'method="action_post", ids=[10]). Common methods: '
            'action_confirm (sales/purchases), action_post (invoices), '
            'action_done (pickings), action_assign (pickings), '
            'action_cancel (most documents). Private methods (starting '
            'with "_") are blocked for safety.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': model_field(),
                'method': {
                    'type': 'string',
                    'description': (
                        'Public method name (e.g. "action_confirm", "action_post", "message_post").'
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
        model: str,
        method: str,
        ids=None,
        args: str | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Resolve the model, browse the target ids and invoke a public method.

        Rejects private methods via :func:`get_public_method`. For non
        ``@api.model`` methods the records to operate on come from ``ids``, or
        else from the first positional argument. A ``context`` key inside
        ``kwargs`` is applied to the recordset rather than passed through.
        """
        target = self._resolve_model(model)
        try:
            unbound = get_public_method(target, method)
        except (AccessError, AttributeError) as exc:
            raise UserError(str(exc))
        target_ids = normalize_ids(ids)
        positional = coerce_json_value(args) or []
        if not getattr(unbound, '_api_model', False):
            if not target_ids and positional:
                target_ids = normalize_ids(positional[0])
                positional = positional[1:]
            if target_ids:
                self._mcp_assert_records_allowed(model, target_ids)
                target = target.browse(target_ids)
        keyword = dict(coerce_json_value(kwargs) or {})
        context_override = keyword.pop('context', None)
        if isinstance(context_override, dict) and context_override:
            target = target.with_context(**context_override)
        return unbound(target, *positional, **keyword)
