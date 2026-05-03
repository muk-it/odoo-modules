import textwrap

from odoo import api, models

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.content import make_content_for_bytes
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
