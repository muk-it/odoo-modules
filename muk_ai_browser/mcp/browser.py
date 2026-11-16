from __future__ import annotations

from typing import Any, NoReturn

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai_browser.tools.schema import (
    CLIENT_META,
    TAB,
    TARGET,
    TRUSTED,
    schema,
)
from odoo.addons.muk_mcp.core.tool import mcp_tool


class BrowserTools(models.AbstractModel):
    """Tools the paired browser extension runs in the user's live tab.

    The extension answers every client-executed tool; a server dispatch raises.
    """

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _client_only(self, name: str) -> NoReturn:
        """Refuse a server dispatch of a tool the browser extension executes.

        :raise UserError: always
        """
        raise UserError(
            _(
                'Tool %(name)s runs in the browser extension, not on the server.',
                name=name,
            ),
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='browser_read_page',
        description=(
            "Read the page open in the user's browser as an accessibility "
            'snapshot: one line per element with its role, name, state and a '
            'ref ("[ref=e12]") the other browser tools act on. Read the page '
            'before acting on it; refs of an older snapshot may be stale.'
        ),
        input_schema=schema(
            viewport_only={
                'type': 'boolean',
                'description': (
                    'Only include elements inside the viewport; by default the '
                    'whole page is read.'
                ),
                'default': False,
            },
            interactive_only={
                'type': 'boolean',
                'description': 'Only include interactive elements.',
                'default': False,
            },
            max_chars={
                'type': 'integer',
                'description': 'Maximum characters of the snapshot.',
                'default': 20000,
            },
            **TAB,
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_read_page(self, **kwargs: Any) -> NoReturn:
        """Read the page snapshot (client-executed)."""
        self._client_only('browser_read_page')

    @api.model
    @mcp_tool(
        name='browser_find',
        description=(
            'Find elements on the whole page whose text, name or role matches '
            'the query, cheaper than reading the full page.'
        ),
        input_schema=schema(
            ['query'],
            query={'type': 'string', 'description': 'Text or role to look for.'},
            max_results={
                'type': 'integer',
                'description': 'Maximum matching elements.',
                'default': 20,
            },
            **TAB,
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_find(self, **kwargs: Any) -> NoReturn:
        """Find elements on the page (client-executed)."""
        self._client_only('browser_find')

    @api.model
    @mcp_tool(
        name='browser_screenshot',
        description=(
            'Take a screenshot of the visible page or of one element. With '
            'marks, every interactive element is numbered by its ref.'
        ),
        input_schema=schema(
            ref=TARGET['ref'],
            marks={
                'type': 'boolean',
                'description': 'Draw the element refs onto the image.',
                'default': False,
            },
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_screenshot(self, **kwargs: Any) -> NoReturn:
        """Capture the page (client-executed)."""
        self._client_only('browser_screenshot')

    @api.model
    @mcp_tool(
        name='browser_scroll',
        description='Scroll the page, or a scrollable element, in a direction.',
        input_schema=schema(
            ['direction'],
            ref=TARGET['ref'],
            direction={'type': 'string', 'enum': ['up', 'down', 'left', 'right']},
            amount_pages={
                'type': 'number',
                'description': 'Viewport pages to scroll.',
                'default': 1,
            },
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_scroll(self, **kwargs: Any) -> NoReturn:
        """Scroll the page (client-executed)."""
        self._client_only('browser_scroll')

    @api.model
    @mcp_tool(
        name='browser_wait_for',
        description=(
            'Wait until a text appears or disappears on the page, or for a fixed time.'
        ),
        input_schema=schema(
            text={'type': 'string', 'description': 'Text to wait for.'},
            text_gone={'type': 'string', 'description': 'Text to wait to vanish.'},
            time_ms={'type': 'integer', 'description': 'Fixed wait.'},
            timeout_ms={'type': 'integer', 'default': 10000},
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_wait_for(self, **kwargs: Any) -> NoReturn:
        """Wait on the page (client-executed)."""
        self._client_only('browser_wait_for')

    @api.model
    @mcp_tool(
        name='browser_tabs',
        description=(
            'List, select, open or close the tabs of the "MuK AI" tab group the '
            'agent works in. The user adds tabs by dragging them into the group; '
            'the agent closes only the tabs it opened.'
        ),
        input_schema=schema(
            ['action'],
            action={'type': 'string', 'enum': ['list', 'select', 'new', 'close']},
            tab_id={'type': 'integer', 'description': 'Tab to select or close.'},
            url={'type': 'string', 'description': 'URL of a new tab.'},
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_tabs(self, **kwargs: Any) -> NoReturn:
        """Manage the agent's tabs (client-executed)."""
        self._client_only('browser_tabs')

    @api.model
    @mcp_tool(
        name='browser_click',
        description='Click an element of the page.',
        input_schema=schema(
            ['ref', 'element'],
            **TARGET,
            button={'type': 'string', 'enum': ['left', 'right', 'middle']},
            double={'type': 'boolean', 'default': False},
            modifiers={
                'type': 'array',
                'items': {
                    'type': 'string',
                    'enum': ['Alt', 'Control', 'Meta', 'Shift'],
                },
            },
            **TRUSTED,
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_click(self, **kwargs: Any) -> NoReturn:
        """Click an element (client-executed)."""
        self._client_only('browser_click')

    @api.model
    @mcp_tool(
        name='browser_type',
        description=(
            'Type text into an editable element, replacing its value. Password '
            'and payment fields are refused: the user fills those in.'
        ),
        input_schema=schema(
            ['ref', 'element', 'text'],
            **TARGET,
            text={'type': 'string'},
            submit={
                'type': 'boolean',
                'description': 'Press Enter afterwards.',
                'default': False,
            },
            **TRUSTED,
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_type(self, **kwargs: Any) -> NoReturn:
        """Type into an element (client-executed)."""
        self._client_only('browser_type')

    @api.model
    @mcp_tool(
        name='browser_fill_form',
        description=(
            'Fill several form fields at once: text inputs, checkboxes, radio '
            'buttons and selects. Nothing is submitted.'
        ),
        input_schema=schema(
            ['fields'],
            fields={
                'type': 'array',
                'items': schema(['ref', 'element', 'value'], **TARGET, value={}),
            },
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_fill_form(self, **kwargs: Any) -> NoReturn:
        """Fill form fields (client-executed)."""
        self._client_only('browser_fill_form')

    @api.model
    @mcp_tool(
        name='browser_select_option',
        description='Select one or more options of a select element.',
        input_schema=schema(
            ['ref', 'element', 'values'],
            **TARGET,
            values={'type': 'array', 'items': {'type': 'string'}},
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_select_option(self, **kwargs: Any) -> NoReturn:
        """Select options (client-executed)."""
        self._client_only('browser_select_option')

    @api.model
    @mcp_tool(
        name='browser_press_key',
        description='Press a key, such as Enter, Escape or ArrowDown.',
        input_schema=schema(
            ['key'],
            key={'type': 'string'},
            **TARGET,
            **TRUSTED,
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_press_key(self, **kwargs: Any) -> NoReturn:
        """Press a key (client-executed)."""
        self._client_only('browser_press_key')

    @api.model
    @mcp_tool(
        name='browser_hover',
        description='Move the pointer over an element.',
        input_schema=schema(['ref', 'element'], **TARGET),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_hover(self, **kwargs: Any) -> NoReturn:
        """Hover an element (client-executed)."""
        self._client_only('browser_hover')

    @api.model
    @mcp_tool(
        name='browser_navigate',
        description=(
            "Open a URL in the agent's tab, or in a new tab of its group. To "
            'follow a link, open its /url from the snapshot; to search the web, '
            'open a search URL such as https://www.google.com/search?q=...'
        ),
        input_schema=schema(
            ['url'],
            url={'type': 'string'},
            new_tab={'type': 'boolean', 'default': False},
        ),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_navigate(self, **kwargs: Any) -> NoReturn:
        """Navigate the tab (client-executed)."""
        self._client_only('browser_navigate')

    @api.model
    @mcp_tool(
        name='browser_navigate_back',
        description='Go back to the previous page of the tab.',
        input_schema=schema(),
        category='read',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_navigate_back(self, **kwargs: Any) -> NoReturn:
        """Go back (client-executed)."""
        self._client_only('browser_navigate_back')

    @api.model
    @mcp_tool(
        name='browser_save_file',
        description=(
            'Save a file from the web as an attachment of an Odoo record: the '
            'file a link or image points to (ref), a file URL, or without both '
            'the page itself when it is a PDF or an image. Returns the attachment.'
        ),
        input_schema=schema(
            ['res_model', 'res_id'],
            ref=TARGET['ref'],
            element=TARGET['element'],
            url={'type': 'string', 'description': 'URL of the file.'},
            res_model={'type': 'string', 'description': 'Model of the record.'},
            res_id={'type': 'integer', 'description': 'Id of the record.'},
            name={'type': 'string', 'description': 'File name to store it under.'},
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_save_file(self, **kwargs: Any) -> NoReturn:
        """Save a web file into Odoo (client-executed)."""
        self._client_only('browser_save_file')

    @api.model
    @mcp_tool(
        name='browser_upload_file',
        description=(
            'Put an Odoo attachment into a file field of the page, marked '
            '[file] in the snapshot, such as an upload on a supplier or customer '
            'portal. The user approves every upload.'
        ),
        input_schema=schema(
            ['ref', 'element', 'attachment_id'],
            **TARGET,
            attachment_id={
                'type': 'integer',
                'description': 'The ir.attachment to upload.',
            },
        ),
        category='write',
        registry='odoo',
        meta=CLIENT_META,
    )
    def _mcp_browser_upload_file(self, **kwargs: Any) -> NoReturn:
        """Upload an Odoo file into the page (client-executed)."""
        self._client_only('browser_upload_file')

    @api.model
    @mcp_tool(
        name='browser_propose_plan',
        description=(
            'Ask the user to approve a plan before a multi-step task in the '
            'browser. Once approved, the actions on the listed sites run '
            'without asking one by one; sensitive actions still ask.'
        ),
        input_schema=schema(
            ['summary', 'steps', 'origins'],
            summary={'type': 'string', 'description': 'What the plan achieves.'},
            steps={'type': 'array', 'items': {'type': 'string'}},
            origins={
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Origins the plan acts on, like https://example.com.',
            },
        ),
        category='write',
        registry='odoo',
    )
    def _mcp_browser_propose_plan(
        self, summary: str, steps: list[str], origins: list[str], **kwargs: Any
    ) -> dict:
        """Record the approved plan on the chat that proposed it.

        :raise UserError: outside a chat, or when ``origins`` lists no site URLs
        """
        session = self._resolve_mcp_session(
            _('A browser plan can only be proposed in a chat.'),
        )
        if not (
            isinstance(origins, list)
            and origins
            and all(map(session._browser_origin_of, origins))
        ):
            raise UserError(
                _(
                    'not run: "origins" must be a list of site URLs, like ["%s"]. '
                    'Call browser_propose_plan again with it.',
                    session.browser_origin or 'https://example.com',
                )
            )
        session.browser_plan = {
            'summary': summary,
            'steps': steps,
            'origins': [session._browser_origin_of(origin) for origin in origins],
        }
        return {'approved': True, 'origins': session.browser_plan['origins']}
