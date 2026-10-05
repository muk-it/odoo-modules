from __future__ import annotations

import datetime
import struct
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

from werkzeug.exceptions import UnsupportedMediaType

from odoo.http import Response, request
from odoo.tools.misc import format_datetime

from odoo.addons.mail.controllers import attachment
from odoo.addons.muk_web_preview.tools import message as mail_message
from odoo.addons.muk_web_preview.tools.compound import CompoundFileError
from odoo.addons.muk_web_preview.tools.preview import (
    MAX_ROWS,
    MAX_THUMBNAIL_ROWS,
    TEXT_MIMETYPES,
    content_security_policy,
    decode_text,
    preview_type,
    read_table,
)


class AttachmentController(attachment.AttachmentController):
    """Render tables and email files through the text preview of attachments."""

    SUPPORTED_TEXT_MIMETYPES = (
        attachment.AttachmentController.SUPPORTED_TEXT_MIMETYPES + TEXT_MIMETYPES
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_remote_url(self) -> str:
        """Return the current preview URL with remote images allowed.

        The link is followed from a sandboxed frame that sends no session
        cookie, so the reader's language and timezone travel with it.
        """
        params = dict(
            request.httprequest.args.items(),
            remote_images=1,
            lang=request.env.lang,
            tz=request.env.user.tz or '',
        )
        return f'{request.httprequest.path}?{urlencode(params)}'

    def _format_date(self, value: object) -> str:
        """Format an email date header in the reader's timezone and language."""
        try:
            date = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return str(value or '')
        if date.tzinfo:
            date = date.astimezone(datetime.UTC).replace(tzinfo=None)
        return format_datetime(request.env, date, tz=request.params.get('tz'))

    def _render_table(self, record, head: bool) -> Response:
        """Render a delimited text file as a table."""
        with record.raw.open() as file:
            raw = file.read(self.TEXTUAL_THUMBNAIL_SIZE) if head else file.read()
        limit = MAX_THUMBNAIL_ROWS if head else MAX_ROWS
        rows, truncated = read_table(decode_text(raw, not head), limit)
        note = (
            request.env._('Only the first %(rows)s rows are shown.', rows=limit)
            if truncated and not head
            else ''
        )
        return request.render(
            'muk_web_preview.content_table',
            {
                'header': rows[0] if rows else [],
                'rows': rows[1:],
                'note': note,
                'head': head,
            },
        )

    def _render_mail(
        self, record, outlook: bool, head: bool, allow_remote: bool
    ) -> Response:
        """Render an email or Outlook file with its headers and attachments.

        :raise UnsupportedMediaType: when the file cannot be read
        """
        with record.raw.open() as file:
            raw = file.read()
        try:
            message = mail_message.parse_message(raw, outlook)
        except (CompoundFileError, struct.error, ValueError) as error:
            raise UnsupportedMediaType() from error
        body, has_remote = mail_message.body(message, allow_remote)
        if request.params.get('lang') in dict(request.env['res.lang'].get_installed()):
            request.update_context(lang=request.params['lang'])
        return request.render(
            'muk_web_preview.content_mail',
            {
                'subject': str(message['Subject'] or ''),
                'sender': str(message['From'] or ''),
                'to': str(message['To'] or ''),
                'cc': str(message['Cc'] or ''),
                'bcc': str(message['Bcc'] or ''),
                'date': self._format_date(message['Date']),
                'body': body,
                'attachments': mail_message.attachments(message),
                'remote_url': (
                    has_remote
                    and not allow_remote
                    and not head
                    and self._get_remote_url()
                ),
                'head': head,
            },
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _render_text_attachment(self, attachment, head=False, unique=False) -> Response:
        """Render tables and emails, leaving every other type to the text preview."""
        kind = preview_type(attachment.name, attachment.mimetype)
        if not kind:
            return super()._render_text_attachment(attachment, head, unique)
        allow_remote = (
            kind != 'table' and not head and request.params.get('remote_images') == '1'
        )
        if kind == 'table':
            response = self._render_table(attachment, head)
        else:
            response = self._render_mail(
                attachment, kind == 'outlook', head, allow_remote
            )
        immutable = bool(unique) and unique == attachment.checksum
        response = self._set_render_with_headers(response, immutable)
        response.headers['Content-Security-Policy'] = content_security_policy(
            allow_remote
        )
        return response
