from __future__ import annotations

import base64

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools.attachment import (
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_TEXT_INLINE_LIMIT_KB,
    IMAGE_MIMETYPES,
    OFFICE_MIMETYPES,
    PDF_MIMETYPE,
    is_text,
    looks_like_text,
    readable_text,
)


class IrAttachment(models.Model):
    """Validate, describe, and materialize attachments for AI consumption."""

    _inherit = 'ir.attachment'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _ai_max_size_bytes(self) -> int:
        """Return the configured maximum upload size in bytes."""
        return int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('web.max_file_upload_size', DEFAULT_MAX_UPLOAD_BYTES)
        )

    @api.model
    def _ai_text_inline_limit_bytes(self) -> int:
        """Return the inline-text size threshold in bytes."""
        return DEFAULT_TEXT_INLINE_LIMIT_KB * 1024

    @api.model
    def _ai_strategy_for(self, mimetype: str) -> str | None:
        """Return the materialization strategy for a mimetype, or ``None``."""
        if mimetype in IMAGE_MIMETYPES:
            return 'image'
        if mimetype == PDF_MIMETYPE:
            return 'file'
        if is_text(mimetype or '') or mimetype in OFFICE_MIMETYPES:
            return 'inline_text'
        return None

    @api.model
    def _ai_check_mimetype(self, mimetype: str) -> None:
        """Raise when the model cannot read the mimetype.

        :raise UserError: when the mimetype is unsupported
        """
        if not self._ai_strategy_for(mimetype):
            raise UserError(
                _(
                    'Attachment type %s is not supported. Attach an image, a PDF, '
                    'a text file or an Office document.',
                    mimetype or '(unknown)',
                )
            )

    @api.model
    def _ai_check_size(self, size: int) -> None:
        """Raise when the byte size exceeds the configured limit.

        :raise UserError: when the size is over the limit
        """
        if size > (limit := self._ai_max_size_bytes()):
            raise UserError(
                _(
                    'Attachment exceeds the %(limit)s MiB size limit.',
                    limit=limit // (1024 * 1024),
                )
            )

    @api.model
    def _ai_store_binary(
        self,
        filename: str,
        mimetype: str,
        data_b64: str,
        res_id: int | None = None,
    ) -> IrAttachment:
        """Create a session attachment from a base64 payload, checking only its size.

        The mimetype allow-list guards what the *model* may ingest, which is a
        narrower question than what may be stored: an XLSX export has no
        ingest strategy, yet the user must still be able to download it.

        :raise UserError: when the payload is not valid base64
        """
        try:
            raw = base64.b64decode(data_b64 or '', validate=True)
        except ValueError as error:
            raise UserError(
                _('Attachment data is not valid base64: %s', error)
            ) from error
        self._ai_check_size(len(raw))
        return self.create(
            {
                'name': filename or 'upload',
                'raw': raw,
                'mimetype': mimetype,
                'res_model': 'muk_ai.session',
                'res_id': res_id or 0,
            }
        )

    @api.model
    def _ai_create_from_upload(
        self,
        filename: str,
        mimetype: str,
        data_b64: str,
        res_id: int | None = None,
    ) -> IrAttachment:
        """Create a session attachment from an uploaded base64 payload.

        A file of a type the model cannot read is kept as plain text when its
        content is text, such as source code with no registered type.
        :raise UserError: when the model cannot read the file
        """
        if not self._ai_strategy_for(mimetype) and looks_like_text(data_b64):
            mimetype = 'text/plain'
        self._ai_check_mimetype(mimetype)
        return self._ai_store_binary(filename, mimetype, data_b64, res_id=res_id)

    def _ai_validate(self) -> None:
        """Check read access, mimetype, and size on each record."""
        for record in self:
            record.check_access_rights('read')
            record.check_access_rule('read')
            record._ai_check_mimetype(record.mimetype)
            record._ai_check_size(record.file_size or 0)

    def _ai_describe(self) -> dict:
        """Return a lightweight descriptor of this attachment."""
        return {
            'id': self.id,
            'filename': self.name,
            'mimetype': self.mimetype,
            'size': self.file_size or 0,
        }

    def _ai_materialize(self) -> dict:
        """Return a content block for this attachment per its strategy."""
        self._ai_validate()
        raw = self.raw or b''
        strategy = self._ai_strategy_for(self.mimetype)
        block = {
            'type': 'muk_ai_attachment',
            'attachment_id': self.id,
            'filename': self.name,
            'mimetype': self.mimetype,
            'strategy': strategy,
        }
        if strategy == 'inline_text':
            limit = self._ai_text_inline_limit_bytes()
            text = (
                self._index(raw, None) or ''
                if self.mimetype in OFFICE_MIMETYPES
                else readable_text(raw, self.mimetype)
            )
            block['inline_text'] = text[:limit]
            block['truncated'] = len(text) > limit
        else:
            block['data_b64'] = base64.b64encode(raw).decode('ascii')
        return block
