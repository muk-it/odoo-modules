from __future__ import annotations

import textwrap

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.content import (
    is_textual_mimetype,
    make_content_for_bytes,
    normalize_mimetype,
)
from odoo.addons.muk_mcp.tools.descriptions import context_field
from odoo.addons.muk_mcp.tools.protocol import (
    ToolContent,
    make_text_content,
)


class MCPMixin(models.AbstractModel):
    """Add the MCP resource-reading tool to the shared MCP mixin."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def READ_RESOURCE_FORMATS(self) -> tuple[str, ...]:
        """Return the resource output formats this mixin can read."""
        return ('auto', 'text', 'resource')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _is_inline_block_mimetype(self, normalized: str) -> bool:
        """Return whether the mimetype is emitted as an inline content block."""
        return is_textual_mimetype(normalized) or normalized.startswith(
            ('image/', 'audio/')
        )

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
            index = self.env['ir.attachment']._index(
                raw,
                mimetype,
            )
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
                _(
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
                  odoo://attachment/<id>               — an ir.attachment row
                  odoo://record/<model>/<id>/<field>   — a Binary field on a record
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
                  auto     — smartest mixed representation (default)
                  text     — extracted text only; fails when not extractable
                  resource — raw bytes only, as an MCP resource block\
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
        if format not in self.READ_RESOURCE_FORMATS:
            raise UserError(
                _(
                    'Unsupported format %(f)r; expected one of: %(opts)s.',
                    f=format,
                    opts=', '.join(self.READ_RESOURCE_FORMATS),
                ),
            )
        mimetype, raw, name = self._resolve_resource_uri(
            uri,
        )
        normalized = normalize_mimetype(mimetype)
        if self._is_inline_block_mimetype(normalized):
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
