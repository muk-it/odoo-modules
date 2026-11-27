from __future__ import annotations

import email
import email.policy
import io
import mimetypes
import zipfile

from PIL import Image

from odoo.tools.pdf import PdfReader

PDF_COLOR_MODES = {'/DeviceRGB': 'RGB', '/DeviceGray': 'L', '/DeviceCMYK': 'CMYK'}

PDF_ICC_MODES = {1: 'L', 3: 'RGB', 4: 'CMYK'}

PDF_IMAGE_FILES = {'/DCTDecode': 'jpg', '/JPXDecode': 'jp2'}

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


def pdf_image(image) -> tuple[str, bytes] | None:
    """Return the extension and file of a PDF image, ``None`` for an unknown format.

    A JPEG stays as stored; any other image is written as a PNG from its samples.
    """
    codec = image.get('/Filter')
    chain = isinstance(codec, list)
    if extension := PDF_IMAGE_FILES.get(codec[-1] if chain else codec):
        return extension, image.getData() if chain else image._data
    space = image.get('/ColorSpace')
    space = space.getObject() if space else None
    if isinstance(space, list) and space[0] == '/ICCBased':
        mode = PDF_ICC_MODES.get(space[1].getObject().get('/N'))
    else:
        mode = PDF_COLOR_MODES.get(space)
    if not mode or image.get('/BitsPerComponent') != 8:
        return None
    output = io.BytesIO()
    size = (image['/Width'], image['/Height'])
    Image.frombytes(mode, size, image.getData()).convert('RGB').save(output, 'PNG')
    return 'png', output.getvalue()


def file_parts(raw: bytes, mimetype: str) -> list[tuple[str, bytes]]:
    """Return the named files a document holds, empty for any other file.

    A PDF holds its embedded images, an email its inline images and
    attachments, an Office document its media.
    """
    if mimetype == 'application/pdf':
        parts = []
        for page, content in enumerate(PdfReader(io.BytesIO(raw)).pages, 1):
            resources = content.get('/Resources')
            objects = resources.getObject().get('/XObject') if resources else None
            for name, image in (objects.getObject() if objects else {}).items():
                image = image.getObject()
                if image.get('/Subtype') == '/Image' and (file := pdf_image(image)):
                    parts.append((f'page-{page}-{name[1:]}.{file[0]}', file[1]))
        return parts
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
