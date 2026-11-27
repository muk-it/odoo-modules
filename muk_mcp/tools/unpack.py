from __future__ import annotations

import email
import email.policy
import io
import mimetypes
import zipfile

from odoo.tools.pdf import PdfReader

OFFICE_MEDIA = {
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': (
        'word/media/'
    ),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xl/media/',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': (
        'ppt/media/'
    ),
    'application/vnd.oasis.opendocument.text': 'Pictures/',
    'application/vnd.oasis.opendocument.spreadsheet': 'Pictures/',
    'application/vnd.oasis.opendocument.presentation': 'Pictures/',
}


def file_parts(raw: bytes, mimetype: str) -> list[tuple[str, bytes]]:
    """Return the named files a document holds, empty for any other file.

    A PDF holds its embedded images when the PDF library lists them (PyPDF2 2.11
    or later), an email its inline images and attachments, an Office document
    its media.
    """
    if mimetype == 'application/pdf':
        return [
            (f'page-{page}-{image.name}', image.data)
            for page, content in enumerate(PdfReader(io.BytesIO(raw)).pages, 1)
            for image in getattr(content, 'images', ())
        ]
    if mimetype == 'message/rfc822':
        message = email.message_from_bytes(raw, policy=email.policy.default)
        return [
            (
                part.get_filename()
                or f'part-{index}{mimetypes.guess_extension(part.get_content_type()) or ""}',
                part.get_payload(decode=True) or b'',
            )
            for index, part in enumerate(message.walk(), 1)
            if not part.is_multipart()
            and (part.get_filename() or part.get_content_maintype() != 'text')
        ]
    if prefix := OFFICE_MEDIA.get(mimetype):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return [
                (info.filename.rsplit('/', 1)[-1], archive.read(info))
                for info in archive.infolist()
                if info.filename.startswith(prefix) and not info.is_dir()
            ]
    return []
