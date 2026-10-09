from __future__ import annotations

import textwrap
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import BinaryBytes

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.models.transfer import TRANSFER_MINUTES
from odoo.addons.muk_mcp.tools.content import (
    is_inline_mimetype,
    make_content_for_bytes,
    normalize_mimetype,
)
from odoo.addons.muk_mcp.tools.descriptions import HTTP_HINT, context_field
from odoo.addons.muk_mcp.tools.protocol import (
    ToolContent,
    make_text_content,
)

READ_RESOURCE_FORMATS = ('auto', 'text', 'resource')


class MCPMixin(models.AbstractModel):
    """Add the MCP resource-reading tools to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _mcp_read_resource_indexed(
        self,
        uri: str,
        mimetype: str | None,
        raw: bytes,
        name: str | None,
        format: str,
    ) -> ToolContent:
        """Build content blocks for an indexable document, combining extracted text and/or the raw blob per ``format``.

        :raise UserError: when ``format`` yields no blocks (text not extractable).
        """
        blocks = []
        if format in ('auto', 'text'):
            index = self.env['ir.attachment']._index(BinaryBytes(raw), mimetype)
            if text := (index or '').strip():
                blocks.append(make_text_content(text))
        if format in ('auto', 'resource'):
            blocks.append(
                make_content_for_bytes(
                    uri,
                    mimetype,
                    raw_bytes=raw,
                    name=name or None,
                ),
            )
        if not blocks:
            raise UserError(
                self.env._(
                    'Could not extract text from %(n)s (%(m)s).\n'
                    'The file may be scanned, encrypted, empty, or not a text-bearing format.\n'
                    'Use format="resource" or format="auto" to get the raw blob.',
                    n=name or uri,
                    m=mimetype or 'unknown',
                ),
            )
        return ToolContent(blocks)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='read_resource',
        description=textwrap.dedent(
            """\
                Fetch the content of a resource by its odoo:// uri and return
                it as one or more typed MCP content blocks. Supported uri
                shapes:
                  odoo://attachment/<id>               - an ir.attachment row
                  odoo://record/<model>/<id>/<field>   - a Binary field on a record
                Textual mimetypes (text/*, application/json, application/xml,
                application/yaml, application/javascript, image/svg+xml, ...)
                return a UTF-8 'text' block. image/* returns an 'image' block.
                audio/* returns an 'audio' block. For binary documents that
                Odoo can index (application/pdf, .docx, .xlsx, .pptx, ODF) the
                default response is BOTH an extracted-text block and the raw
                bytes as a 'resource' block, so clients that cannot render the
                blob still get the content. Use the 'format' arg to override.
                Everything else returns a single 'resource' block with a
                base64 blob. Access is enforced by the user's normal ACL on
                the underlying attachment or record.

                Supported 'format' values (apply to indexable documents;
                ignored for text/image/audio):
                  auto     - smartest mixed representation (default)
                  text     - extracted text only; fails when not extractable
                  resource - raw bytes only, as an MCP resource block\
            """,
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'uri': {
                    'type': 'string',
                    'description': (
                        'Resource uri. Examples: "odoo://attachment/42", '
                        '"odoo://record/res.partner/5/image_1920".'
                    ),
                },
                'format': {
                    'type': 'string',
                    'description': (
                        'Output format for indexable binary documents '
                        '(PDF, docx, xlsx, pptx, ODF). Ignored for '
                        'text/image/audio. One of: "auto" (default), '
                        '"text", "resource". See the tool description '
                        'for semantics.'
                    ),
                    'default': 'auto',
                },
                'context': context_field(),
            },
            'required': ['uri'],
        },
        category='read',
    )
    def _mcp_read_resource(self, uri: str, format: str = 'auto') -> ToolContent:
        """Fetch the resource at ``uri`` and return it as typed content blocks, dispatching by mimetype.

        :raise UserError: when ``format`` is not one of ``READ_RESOURCE_FORMATS``.
        """
        if format not in READ_RESOURCE_FORMATS:
            raise UserError(
                self.env._(
                    'Unsupported format %(f)r; expected one of: %(opts)s.',
                    f=format,
                    opts=', '.join(READ_RESOURCE_FORMATS),
                ),
            )
        mimetype, raw, name = self._resolve_resource_uri(uri)
        if is_inline_mimetype(normalize_mimetype(mimetype)):
            return ToolContent(
                [
                    make_content_for_bytes(
                        uri,
                        mimetype,
                        raw_bytes=raw,
                        name=name or None,
                    ),
                ],
            )
        return self._mcp_read_resource_indexed(
            uri,
            mimetype,
            raw,
            name,
            format,
        )

    @api.model
    @mcp_tool(
        name='authorize_download',
        description=(
            'Get a one-time link to download a file over plain HTTP: an '
            'attachment (odoo://attachment/<id>) or a binary field '
            '(odoo://record/<model>/<id>/<field>). Fetch it with an HTTP GET '
            f'(curl -o <path> <url>) within {TRANSFER_MINUTES} minutes. '
            + HTTP_HINT
            + ' To read '
            'the content into the conversation, use read_resource instead.'
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
