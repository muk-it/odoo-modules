import textwrap

from odoo import api, fields, models

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.models.transfer import TRANSFER_MINUTES
from odoo.addons.muk_mcp.tools.content import make_content_for_bytes
from odoo.addons.muk_mcp.tools.descriptions import HTTP_HINT, context_field
from odoo.addons.muk_mcp.tools.protocol import ToolContent


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='read_resource',
        description=textwrap.dedent(
            """\
                Fetch the content of a resource by its odoo:// uri and return it
                as a typed MCP content block. Supported uri shapes:
                  odoo://attachment/<id>               — an ir.attachment row
                  odoo://record/<model>/<id>/<field>   — a Binary field on a record
                Textual mimetypes (text/*, application/json, application/xml,
                application/yaml, application/javascript, image/svg+xml, ...)
                return a UTF-8 'text' block. image/* returns an 'image' block.
                audio/* returns an 'audio' block. Everything else returns a
                'resource' block with a base64 blob. Access is enforced by the
                user's normal ACL on the underlying attachment or record.\
            """
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'uri': {
                    'type': 'string',
                    'description': (
                        "Resource uri. Examples: 'odoo://attachment/42', "
                        "'odoo://record/res.partner/5/image_1920'."
                    ),
                },
            },
            'required': ['uri'],
        },
        category='read',
    )
    def _mcp_read_resource(self, uri):
        mimetype, raw, name = self._resolve_resource_uri(uri)
        return ToolContent([make_content_for_bytes(
            uri, mimetype, raw_bytes=raw, name=name or None,
        )])

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
            'properties': {
                'uri': {
                    'type': 'string',
                    'description': (
                        'Resource uri, e.g. "odoo://attachment/42" or '
                        '"odoo://record/res.partner/5/image_1920".'
                    ),
                },
                'context': context_field(),
            },
            'required': ['uri'],
        },
        category='read',
        registry='mcp',
    )
    def _mcp_authorize_download(self, uri):
        """Check the resource is readable and issue the link that streams it."""
        self._resolve_resource_target(uri)
        transfer, url = self.env['muk_mcp.transfer']._issue('download', uri=uri)
        return {
            'download_url': url,
            'method': 'GET',
            'expires_at': fields.Datetime.to_string(transfer.expires_at),
            'example': f'curl -o "<path>" "{url}"',
        }
