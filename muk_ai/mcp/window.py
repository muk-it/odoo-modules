from __future__ import annotations

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.parser import coerce_json_value


class AIWindow(models.AbstractModel):
    """Expose Odoo window/action navigation as MCP tools."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _view_types(self) -> list[str]:
        """Return the view type codes registered on ``ir.ui.view``."""
        return [
            code for code, _label in self.env['ir.ui.view']._fields['type'].selection
        ]

    @api.model
    def _window_targets(self) -> list[str]:
        """Return the window target codes for ``ir.actions.act_window``."""
        return [
            code
            for code, _label in self.env['ir.actions.act_window']
            ._fields['target']
            .selection
        ]

    @api.model
    def _resolve_window_action(self, action_ref) -> models.BaseModel | None:
        """Resolve an action reference (id or xmlid) to its record."""
        if isinstance(action_ref, int):
            return (
                self.env['ir.actions.actions']
                .sudo()
                .browse(
                    action_ref,
                )
            )
        if isinstance(action_ref, str) and (ref := action_ref.strip()) and '.' in ref:
            return self.env.ref(ref, raise_if_not_found=False)
        return None

    def _check_view_type(self, view_type) -> str:
        """Validate and normalize a view type, mapping ``tree`` to ``list``.

        :raise UserError: when the view type is not registered.
        """
        if view_type == 'tree':
            view_type = 'list'
        if view_type not in (valid := self._view_types()):
            raise UserError(
                _(
                    'Unknown view_type %(value)r. Valid: %(valid)s.',
                    value=view_type,
                    valid=', '.join(valid),
                )
            )
        return view_type

    def _check_window_target(self, target) -> None:
        """Validate a window action target against the registered codes.

        :raise UserError: when the target is not registered.
        """
        if target not in (valid := self._window_targets()):
            raise UserError(
                _(
                    'Unknown target %(value)r. Valid: %(valid)s.',
                    value=target,
                    valid=', '.join(valid),
                )
            )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='open_record',
        description=(
            'Open a specific record in the Odoo web client for the user. '
            'Use this to navigate the user to a record they need to see '
            'or edit (e.g. open the sale order you just confirmed, the '
            'partner you just created). Returns an ir.actions.act_window '
            'descriptor which the chat UI dispatches automatically. '
            'Only available inside the in-Odoo AI agent — MCP clients '
            'cannot render UI actions.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': 'Technical model name (e.g. "res.partner").',
                },
                'res_id': {
                    'type': 'integer',
                    'description': 'ID of the record to open.',
                },
                'view_type': {
                    'type': 'string',
                    'description': (
                        'View type registered on ir.ui.view '
                        '(e.g. "form", "list", "kanban"). '
                        'Default: "form".'
                    ),
                    'default': 'form',
                },
                'target': {
                    'type': 'string',
                    'description': (
                        'Window target registered on ir.actions.act_window '
                        '(e.g. "current", "new"). Default: "current".'
                    ),
                    'default': 'current',
                },
            },
            'required': ['model', 'res_id'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_open_record(
        self,
        model,
        res_id,
        view_type='form',
        target='current',
    ) -> dict:
        """Return an act_window descriptor opening one record for the user."""
        target_model = self._resolve_model(model)
        target_model.browse(int(res_id)).check_access('read')
        view_type = self._check_view_type(view_type)
        self._check_window_target(target)
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'res_id': int(res_id),
            'view_mode': view_type,
            'views': [[False, view_type]],
            'target': target,
        }

    @api.model
    @mcp_tool(
        name='open_view',
        description=(
            'Open a filtered list/kanban/pivot/graph view of a model for the user. '
            'Use this to show a group of records (e.g. "all unpaid invoices") without '
            'picking one. Returns an ir.actions.act_window descriptor which the chat '
            'UI dispatches. AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'view_type': {
                    'type': 'string',
                    'description': (
                        'Primary view type registered on ir.ui.view '
                        '(e.g. "list", "kanban", "pivot"). Default: "list".'
                    ),
                    'default': 'list',
                },
                'domain': {
                    'type': 'string',
                    'description': (
                        'JSON-encoded Odoo domain to pre-filter the view. '
                        'Pass "[]" or omit for no filter.'
                    ),
                },
                'name': {
                    'type': 'string',
                    'description': 'Optional breadcrumb/title.',
                },
                'target': {
                    'type': 'string',
                    'description': (
                        'Window target registered on ir.actions.act_window.'
                    ),
                    'default': 'current',
                },
                'additional_context': {
                    'type': 'object',
                    'description': (
                        'Extra context keys merged onto the action '
                        '(e.g. {"pivot_row_groupby": ["partner_id"], '
                        '"pivot_measures": ["amount_total"]}, '
                        '{"graph_mode": "bar", "graph_groupbys": '
                        '["user_id"], "graph_measure": "amount_total"}, '
                        '{"search_default_my_quotation": 1}).'
                    ),
                },
            },
            'required': ['model'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_open_view(
        self,
        model,
        view_type='list',
        domain=None,
        name=None,
        target='current',
        additional_context=None,
    ) -> dict:
        """Return an act_window descriptor opening a filtered view of a model."""
        self._resolve_model(model)
        self._check_window_target(target)
        view_type = self._check_view_type(view_type)
        action = {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': view_type,
            'views': [[False, view_type]],
            'domain': coerce_json_value(domain) or [],
            'target': target,
        }
        if name:
            action['name'] = name
        if isinstance(additional_context, dict) and additional_context:
            action['context'] = dict(additional_context)
        return action

    @api.model
    @mcp_tool(
        name='open_action',
        description=(
            'Launch an existing Odoo action for the user by xmlid or id '
            '(e.g. "sale.action_orders" to open the sales order list). '
            'Use this when a matching menu/action already exists and you '
            'want to hand the user to it. Returns the full action '
            'descriptor which the chat UI dispatches. AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'action_ref': {
                    'type': ['string', 'integer'],
                    'description': (
                        'Action xmlid (e.g. "sale.action_orders") or '
                        'numeric id of an ir.actions.actions record.'
                    ),
                },
                'additional_context': {
                    'type': 'object',
                    'description': (
                        "Extra context keys merged into the action's "
                        "context (e.g. {'default_partner_id': 42})."
                    ),
                },
            },
            'required': ['action_ref'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_open_action(self, action_ref, additional_context=None) -> dict:
        """Return the full descriptor of an existing Odoo action for the user."""
        action = self._resolve_window_action(action_ref)
        if (
            action._name == 'ir.actions.actions'
            and action.type
            and action.type != 'ir.actions.actions'
        ):
            concrete = (
                self.env[action.type]
                .sudo()
                .browse(
                    action.id,
                )
            )
            if concrete.exists():
                action = concrete
        descriptor = action._get_action_dict()
        if not descriptor.get('type'):
            descriptor['type'] = action._name
        if additional_context:
            merged = descriptor.get('context') or {}
            if not isinstance(merged, dict):
                merged = {}
            merged = {**merged, **additional_context}
            descriptor['context'] = merged
        return descriptor
