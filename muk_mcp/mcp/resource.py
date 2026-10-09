from __future__ import annotations

from typing import Any

from odoo import api, fields, models

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.models.transfer import TRANSFER_MINUTES
from odoo.addons.muk_mcp.tools.content import make_content_for_bytes
from odoo.addons.muk_mcp.tools.descriptions import HTTP_HINT
from odoo.addons.muk_mcp.tools.protocol import ToolContent

URI_FIELD = {
    'type': 'string',
    'description': (
        'Resource uri, e.g. "odoo://attachment/42" or '
        '"odoo://record/res.partner/5/image_1920".'
    ),
}


class MCPMixin(models.AbstractModel):
    """Add the file reading and download tools to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='read_resource',
        description=(
            'Read a file by its odoo:// uri: an attachment '
            '(odoo://attachment/<id>) or a binary field '
            '(odoo://record/<model>/<id>/<field>). Text comes back as text, '
            'images and audio as such, anything else as a base64 resource.'
        ),
        input_schema={
            'type': 'object',
            'properties': {'uri': URI_FIELD},
            'required': ['uri'],
        },
        category='read',
    )
    def _mcp_read_resource(self, uri: str) -> ToolContent:
        """Return the file behind ``uri`` as an MCP content block."""
        mimetype, raw, name = self._resolve_resource_uri(uri)
        return ToolContent([make_content_for_bytes(uri, mimetype, raw, name or None)])

    @api.model
    @mcp_tool(
        name='authorize_download',
        description=(
            'Get a one-time link to download a file over plain HTTP: an '
            'attachment (odoo://attachment/<id>) or a binary field '
            '(odoo://record/<model>/<id>/<field>). Fetch it with an HTTP GET '
            f'(curl -o <path> <url>) within {TRANSFER_MINUTES} minutes. '
            + HTTP_HINT
            + ' To read the content into the conversation, use read_resource '
            'instead.'
        ),
        input_schema={
            'type': 'object',
            'properties': {'uri': URI_FIELD},
            'required': ['uri'],
        },
        category='read',
        registry='mcp',
    )
    def _mcp_authorize_download(self, uri: str) -> dict[str, Any]:
        """Check the resource is readable and issue the link that streams it."""
        self._resolve_resource_target(uri)
        transfer, url = self.env['muk_mcp.transfer']._issue('download', uri=uri)
        return {
            'download_url': url,
            'method': 'GET',
            'expires_at': fields.Datetime.to_string(transfer.expires_at),
            'example': f'curl -o "<path>" "{url}"',
        }
