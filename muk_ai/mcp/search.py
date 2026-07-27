from __future__ import annotations

from typing import Any, NoReturn

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool

CLIENT_META = {'execute': 'client', 'client': 'webclient'}


class AISearch(models.AbstractModel):
    """Client-executed tool adjusting the live view under the chat window.

    ``adjust_search`` is registered with ``meta={'execute': 'client',
    'client': 'webclient'}`` so the MuK AI session loop pauses and hands
    execution to the webclient tab holding the session's chat window, which
    mutates the active search model and posts the applied changes back. The
    server-side body must never run; it raises to make a stray server
    dispatch loud rather than silent.
    """

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='adjust_search',
        description=(
            'Adjust the view the user is currently looking at (the one '
            'under the chat window): activate filters and group-bys, apply '
            'field searches, add a custom domain, remove active facets, '
            'switch the view type, or change graph/pivot measures and '
            'display options. Use it to refine what the user already sees '
            'instead of opening a new view (e.g. "group these orders by '
            'salesperson", "only show drafts", "switch to a bar chart"). '
            'Returns the changes actually applied plus the available '
            'filter/group-by names when a requested name does not exist, '
            'so you can retry with a valid one. Only works while the user '
            'has a list, kanban, pivot or graph view open in the tab that '
            'hosts this chat. AI-agent only.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'filters': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Search-view filter names to activate '
                        '(e.g. ["draft", "my_orders"]).'
                    ),
                },
                'group_bys': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Field names to group the view by. Uses the '
                        'matching search-view group-by when one exists, '
                        'else groups by the raw field. Date fields accept '
                        'an interval suffix (e.g. "date_order:month").'
                    ),
                },
                'searches': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Field text searches as "field=value" pairs '
                        '(e.g. ["partner_id=Azure"]).'
                    ),
                },
                'custom_domain': {
                    'type': 'string',
                    'description': (
                        'JSON-encoded Odoo domain added as a custom '
                        'filter facet (e.g. '
                        '"[[\\"amount_total\\", \\">=\\", 500]]").'
                    ),
                },
                'remove_facets': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Names of active filters/group-bys/facets to '
                        'remove. Pass "*" to clear all facets.'
                    ),
                },
                'view_type': {
                    'type': 'string',
                    'description': (
                        'Switch to this view type first (e.g. "list", '
                        '"kanban", "pivot", "graph"). Must be available '
                        'on the current action.'
                    ),
                },
                'measures': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': (
                        'Measure field names to activate on a pivot or '
                        'graph view (graph views use only the first).'
                    ),
                },
                'mode': {
                    'type': 'string',
                    'description': 'Graph chart type: "bar", "line" or "pie".',
                },
                'order': {
                    'type': 'string',
                    'description': 'Graph sort order: "ASC" or "DESC".',
                },
                'stacked': {
                    'type': 'boolean',
                    'description': 'Stack the graph series (bar/line).',
                },
                'cumulated': {
                    'type': 'boolean',
                    'description': 'Cumulate the graph values.',
                },
            },
            'required': [],
        },
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_adjust_search(self, **kwargs: Any) -> NoReturn:
        """Adjust the active view's search model (client-executed)."""
        raise UserError(
            _(
                'Tool adjust_search is client-executed and must run in the '
                'webclient tab holding the chat window, not on the server.',
            ),
        )
