from __future__ import annotations

from typing import Any, NoReturn

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool

CLIENT_META = {'execute': 'client', 'client': 'browser'}


class BrowserTools(models.AbstractModel):
    """Client-executed browser perception and action tools.

    Every tool here is registered with ``meta={'execute': 'client',
    'client': 'browser'}`` so the MuK AI session loop pauses and delegates
    execution to the paired browser extension. The server-side bodies must
    never run; they raise to make a stray server dispatch loud rather than
    silent.
    """

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _client_only(self, name: str) -> NoReturn:
        """Raise because a client-executed tool must run in the browser, not the server.

        :raise UserError: always
        """
        raise UserError(
            _(
                'Tool %(name)s is client-executed and must run in the browser.',
                name=name,
            ),
        )

    # ----------------------------------------------------------
    # Read tools
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='read_page',
        description=(
            'Read an accessibility snapshot of the current page as an indexed '
            'tree of roles, names and states with stable element refs.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'viewport_only': {
                    'type': 'boolean',
                    'description': 'Only include elements within the viewport.',
                    'default': True,
                },
                'interactive_only': {
                    'type': 'boolean',
                    'description': 'Only include interactive elements.',
                    'default': False,
                },
                'max_chars': {
                    'type': 'integer',
                    'description': 'Maximum characters of the snapshot to return.',
                    'default': 20000,
                },
            },
        },
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_read_page(self, **kwargs: Any) -> NoReturn:
        """Return the accessibility snapshot of the current page (client-executed)."""
        self._client_only('read_page')

    @api.model
    @mcp_tool(
        name='scroll',
        description='Scroll the page or a referenced element in a direction.',
        input_schema={
            'type': 'object',
            'properties': {
                'ref': {
                    'type': 'string',
                    'description': 'Ref of the element to scroll; omit for the page.',
                },
                'direction': {
                    'type': 'string',
                    'enum': ['up', 'down', 'left', 'right'],
                    'description': 'Scroll direction.',
                },
                'amount_pages': {
                    'type': 'number',
                    'description': 'Number of viewport pages to scroll.',
                    'default': 1,
                },
            },
            'required': ['direction'],
        },
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_scroll(self, **kwargs: Any) -> NoReturn:
        """Scroll the page or a referenced element (client-executed)."""
        self._client_only('scroll')

    @api.model
    @mcp_tool(
        name='hover',
        description='Hover the pointer over a referenced element.',
        input_schema={
            'type': 'object',
            'properties': {
                'element': {
                    'type': 'string',
                    'description': 'Human-readable description of the element.',
                },
                'ref': {
                    'type': 'string',
                    'description': 'Ref of the element to hover.',
                },
            },
            'required': ['element', 'ref'],
        },
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_hover(self, **kwargs: Any) -> NoReturn:
        """Hover over a referenced element (client-executed)."""
        self._client_only('hover')

    @api.model
    @mcp_tool(
        name='wait_for',
        description='Wait for text to appear or disappear, or for a fixed delay.',
        input_schema={
            'type': 'object',
            'properties': {
                'text': {
                    'type': 'string',
                    'description': 'Text to wait for to appear.',
                },
                'text_gone': {
                    'type': 'string',
                    'description': 'Text to wait for to disappear.',
                },
                'time_ms': {
                    'type': 'integer',
                    'description': 'Fixed delay in milliseconds.',
                },
                'timeout_ms': {
                    'type': 'integer',
                    'description': 'Maximum time to wait in milliseconds.',
                    'default': 10000,
                },
            },
        },
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_wait_for(self, **kwargs: Any) -> NoReturn:
        """Wait for a page condition or delay (client-executed)."""
        self._client_only('wait_for')

    @api.model
    @mcp_tool(
        name='screenshot',
        description=(
            'Capture a screenshot of the page, optionally with numbered marks '
            'over interactive elements for set-of-marks grounding.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'marks': {
                    'type': 'boolean',
                    'description': 'Overlay numbered marks on interactive elements.',
                    'default': False,
                },
                'full_page': {
                    'type': 'boolean',
                    'description': 'Capture the full scrollable page.',
                    'default': False,
                },
                'ref': {
                    'type': 'string',
                    'description': 'Ref of an element to capture; omit for the viewport.',
                },
            },
        },
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_screenshot(self, **kwargs: Any) -> NoReturn:
        """Capture a page screenshot (client-executed)."""
        self._client_only('screenshot')

    # ----------------------------------------------------------
    # Write tools
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='click',
        description='Click a referenced element, optionally double or with modifiers.',
        input_schema={
            'type': 'object',
            'properties': {
                'element': {
                    'type': 'string',
                    'description': 'Human-readable description of the element.',
                },
                'ref': {
                    'type': 'string',
                    'description': 'Ref of the element to click.',
                },
                'button': {
                    'type': 'string',
                    'enum': ['left', 'right', 'middle'],
                    'description': 'Mouse button to use.',
                    'default': 'left',
                },
                'double': {
                    'type': 'boolean',
                    'description': 'Perform a double click.',
                    'default': False,
                },
                'modifiers': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': ['Alt', 'Control', 'Meta', 'Shift'],
                    },
                    'description': 'Modifier keys held during the click.',
                },
            },
            'required': ['element', 'ref'],
        },
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_click(self, **kwargs: Any) -> NoReturn:
        """Click a referenced element (client-executed)."""
        self._client_only('click')

    @api.model
    @mcp_tool(
        name='fill',
        description='Fill a referenced input with text, optionally submitting it.',
        input_schema={
            'type': 'object',
            'properties': {
                'element': {
                    'type': 'string',
                    'description': 'Human-readable description of the element.',
                },
                'ref': {
                    'type': 'string',
                    'description': 'Ref of the input to fill.',
                },
                'text': {
                    'type': 'string',
                    'description': 'Text to type into the input.',
                },
                'submit': {
                    'type': 'boolean',
                    'description': 'Press Enter after filling.',
                    'default': False,
                },
            },
            'required': ['element', 'ref', 'text'],
        },
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_fill(self, **kwargs: Any) -> NoReturn:
        """Fill a referenced input with text (client-executed)."""
        self._client_only('fill')

    @api.model
    @mcp_tool(
        name='select_option',
        description='Select one or more options in a referenced dropdown.',
        input_schema={
            'type': 'object',
            'properties': {
                'element': {
                    'type': 'string',
                    'description': 'Human-readable description of the element.',
                },
                'ref': {
                    'type': 'string',
                    'description': 'Ref of the select element.',
                },
                'values': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Option values or labels to select.',
                },
            },
            'required': ['element', 'ref', 'values'],
        },
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_select_option(self, **kwargs: Any) -> NoReturn:
        """Select options in a referenced dropdown (client-executed)."""
        self._client_only('select_option')

    @api.model
    @mcp_tool(
        name='press_key',
        description='Press a single key, optionally focused on a referenced element.',
        input_schema={
            'type': 'object',
            'properties': {
                'key': {
                    'type': 'string',
                    'description': 'Key name to press (e.g. Enter, ArrowDown, a).',
                },
                'ref': {
                    'type': 'string',
                    'description': 'Ref of the element to focus before pressing.',
                },
            },
            'required': ['key'],
        },
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_press_key(self, **kwargs: Any) -> NoReturn:
        """Press a key (client-executed)."""
        self._client_only('press_key')

    @api.model
    @mcp_tool(
        name='navigate',
        description='Navigate the active tab to a URL.',
        input_schema={
            'type': 'object',
            'properties': {
                'url': {
                    'type': 'string',
                    'format': 'uri',
                    'description': 'Absolute URL to navigate to.',
                },
            },
            'required': ['url'],
        },
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_navigate(self, **kwargs: Any) -> NoReturn:
        """Navigate the active tab to a URL (client-executed)."""
        self._client_only('navigate')

    @api.model
    @mcp_tool(
        name='navigate_back',
        description='Navigate the active tab back to the previous page.',
        input_schema={
            'type': 'object',
            'properties': {},
        },
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _browser_navigate_back(self, **kwargs: Any) -> NoReturn:
        """Navigate the active tab back (client-executed)."""
        self._client_only('navigate_back')
