from __future__ import annotations

import base64
import email
import email.policy
from email.message import EmailMessage

import lxml.html
from markupsafe import Markup

from odoo.tools.mail import html_remove_links, html_sanitize
from odoo.tools.misc import human_size

from odoo.addons.muk_web_preview.tools.outlook import OutlookMessage


def parse_message(raw: bytes, outlook: bool) -> EmailMessage:
    """Parse an email file, or an Outlook item file when ``outlook`` is set.

    :raise CompoundFileError: when an Outlook file cannot be read
    """
    if outlook:
        return OutlookMessage.from_bytes(raw).to_email()
    return email.message_from_bytes(raw, policy=email.policy.default)


def part_text(part: EmailMessage) -> str:
    """Return the text of a body part, decoding leniently on bad charsets."""
    try:
        return part.get_content()
    except (LookupError, UnicodeError, ValueError):
        payload = part.get_payload(decode=True) or b''
        return payload.decode('utf-8', errors='replace')


def inline_images(message: EmailMessage) -> dict[str, str]:
    """Map the content ids of embedded images to data URLs."""
    images = {}
    for part in message.walk():
        cid = (part['Content-ID'] or '').strip('<> ')
        if cid and part.get_content_maintype() == 'image':
            data = part.get_payload(decode=True) or b''
            images[cid] = (
                f'data:{part.get_content_type()};base64,'
                f'{base64.b64encode(data).decode()}'
            )
    return images


def attachments(message: EmailMessage) -> list[dict]:
    """List the attached files with their name and size."""
    result = []
    for part in message.iter_attachments():
        if part['Content-ID'] and part.get_content_maintype() == 'image':
            continue
        if part.get_content_type() == 'message/rfc822':
            nested = part.get_payload(0)
            name = part.get_filename() or str(nested['Subject'] or '')
            size = len(nested.as_bytes())
        else:
            name = part.get_filename()
            size = len(part.get_payload(decode=True) or b'')
        result.append({'name': name or 'attachment', 'size': human_size(size)})
    return result


def body(message: EmailMessage, allow_remote: bool) -> tuple[Markup, bool]:
    """Sanitize the body, inline its images and find remote content.

    :return: the body and whether it references remote images
    """
    part = message.get_body(preferencelist=('html', 'plain'))
    if part is None:
        return Markup(), False
    content = part_text(part)
    if part.get_content_type() != 'text/html':
        content = Markup('<pre>%s</pre>') % content
    html = html_remove_links(html_sanitize(content))
    if not html or not html.strip():
        return Markup(), False
    root = lxml.html.fragment_fromstring(html, create_parent='div')
    images = inline_images(message)
    has_remote = False
    for node in root.iter('img'):
        src = (node.get('src') or '').strip()
        if src.startswith('cid:') and src[4:] in images:
            node.set('src', images[src[4:]])
        elif src.startswith(('http:', 'https:', '//')):
            has_remote = True
            if not allow_remote:
                node.set('data-src', src)
                node.attrib.pop('src')
    return Markup(lxml.html.tostring(root, encoding='unicode')[5:-6]), has_remote
