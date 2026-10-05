from __future__ import annotations

import datetime
import struct
from email.message import EmailMessage
from email.utils import format_datetime, formataddr

from odoo.addons.muk_web_preview.tools.compound import CompoundFile
from odoo.addons.muk_web_preview.tools.rtf import codec_name, decompress, extract_html

PT_LONG = 0x0003
PT_OBJECT = 0x000D
PT_STRING8 = 0x001E
PT_UNICODE = 0x001F
PT_SYSTIME = 0x0040
PT_BINARY = 0x0102

PR_SUBJECT = 0x0037
PR_CLIENT_SUBMIT_TIME = 0x0039
PR_RECIPIENT_TYPE = 0x0C15
PR_SENDER_NAME = 0x0C1A
PR_SENDER_EMAIL_ADDRESS = 0x0C1F
PR_MESSAGE_DELIVERY_TIME = 0x0E06
PR_BODY = 0x1000
PR_RTF_COMPRESSED = 0x1009
PR_HTML = 0x1013
PR_DISPLAY_NAME = 0x3001
PR_EMAIL_ADDRESS = 0x3003
PR_CREATION_TIME = 0x3007
PR_ATTACH_DATA = 0x3701
PR_ATTACH_FILENAME = 0x3704
PR_ATTACH_METHOD = 0x3705
PR_ATTACH_LONG_FILENAME = 0x3707
PR_ATTACH_MIME_TAG = 0x370E
PR_ATTACH_CONTENT_ID = 0x3712
PR_SMTP_ADDRESS = 0x39FE
PR_INTERNET_CPID = 0x3FDE
PR_MESSAGE_LOCALE_ID = 0x3FF1
PR_MESSAGE_CODEPAGE = 0x3FFD
PR_SENDER_SMTP_ADDRESS = 0x5D01

LOCALE_CODEPAGES = {
    0x01: 1256,
    0x02: 1251,
    0x05: 1250,
    0x08: 1253,
    0x0D: 1255,
    0x0E: 1250,
    0x11: 932,
    0x12: 949,
    0x15: 1250,
    0x18: 1250,
    0x19: 1251,
    0x1A: 1250,
    0x1B: 1250,
    0x1E: 874,
    0x1F: 1254,
    0x22: 1251,
    0x23: 1251,
    0x24: 1250,
    0x25: 1257,
    0x26: 1257,
    0x27: 1257,
    0x2A: 1258,
}

ATTACH_EMBEDDED_MSG = 5
RECIPIENT_HEADERS = {1: 'To', 2: 'Cc', 3: 'Bcc'}

ROOT_HEADER_SIZE = 32
EMBEDDED_HEADER_SIZE = 24
CHILD_HEADER_SIZE = 8

FILETIME_EPOCH = datetime.datetime(1601, 1, 1, tzinfo=datetime.UTC)


class OutlookMessage:
    """Read an Outlook item file (MS-OXMSG) and convert it to an email message."""

    def __init__(
        self,
        compound: CompoundFile,
        path: str = '',
        header_size: int = ROOT_HEADER_SIZE,
    ) -> None:
        """Load the fixed size properties of the message stored at ``path``."""
        self._compound = compound
        self._path = path
        self._properties = self._read_properties(path, header_size)
        locale = self._properties.get(PR_MESSAGE_LOCALE_ID, 0) & 0x3FF
        self._codec = codec_name(
            self._properties.get(PR_MESSAGE_CODEPAGE) or LOCALE_CODEPAGES.get(locale)
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> OutlookMessage:
        """Open an Outlook item file from its raw content.

        :raise CompoundFileError: when the data is not a compound file
        """
        return cls(CompoundFile(data))

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _read_properties(self, path: str, header_size: int) -> dict[int, int]:
        """Parse the inline values of a property stream by property id."""
        raw = self._compound.read(f'{path}/__properties_version1.0') or b''
        properties = {}
        for offset in range(header_size, len(raw) - 15, 16):
            tag, _flags, value = struct.unpack_from('<IIQ', raw, offset)
            if tag & 0xFFFF in (PT_LONG, PT_SYSTIME):
                properties[tag >> 16] = value
        return properties

    def _read(self, path: str, prop_id: int, prop_type: int) -> bytes | None:
        """Return the raw stream of a variable length property."""
        return self._compound.read(f'{path}/__substg1.0_{prop_id:04X}{prop_type:04X}')

    def _string(self, prop_id: int, path: str | None = None) -> str:
        """Return a string property in either of its two encodings."""
        path = self._path if path is None else path
        raw = self._read(path, prop_id, PT_UNICODE)
        if raw is not None:
            return raw.decode('utf-16-le', errors='replace').rstrip('\x00')
        raw = self._read(path, prop_id, PT_STRING8)
        if raw is not None:
            return raw.decode(self._codec, errors='replace').rstrip('\x00')
        return ''

    def _children(self, prefix: str) -> list[str]:
        """Return the paths of the recipient or attachment storages."""
        return [
            f'{self._path}/{name}'
            for name in self._compound.listdir(self._path)
            if name.startswith(prefix)
        ]

    def _address(self, name: str, address: str) -> str:
        """Format a display name and an SMTP address as one header value."""
        if '@' not in address:
            return name or address
        return formataddr((name, address))

    def _sender(self) -> str:
        """Return the formatted sender of the message."""
        address = self._string(PR_SENDER_SMTP_ADDRESS) or self._string(
            PR_SENDER_EMAIL_ADDRESS
        )
        return self._address(self._string(PR_SENDER_NAME), address)

    def _recipients(self) -> dict[str, list[str]]:
        """Group the formatted recipients by their header name."""
        recipients = {}
        for path in self._children('__recip_version1.0_#'):
            kind = self._read_properties(path, CHILD_HEADER_SIZE).get(PR_RECIPIENT_TYPE)
            address = self._string(PR_SMTP_ADDRESS, path) or self._string(
                PR_EMAIL_ADDRESS, path
            )
            recipients.setdefault(RECIPIENT_HEADERS.get(kind, 'To'), []).append(
                self._address(self._string(PR_DISPLAY_NAME, path), address)
            )
        return recipients

    def _date(self) -> datetime.datetime | None:
        """Return the time the message was sent, received or created."""
        for prop_id in (
            PR_CLIENT_SUBMIT_TIME,
            PR_MESSAGE_DELIVERY_TIME,
            PR_CREATION_TIME,
        ):
            if value := self._properties.get(prop_id):
                return FILETIME_EPOCH + datetime.timedelta(microseconds=value // 10)
        return None

    def _html(self) -> str | None:
        """Return the HTML body, unwrapping it from the RTF body if needed."""
        raw = self._read(self._path, PR_HTML, PT_BINARY)
        if raw:
            codepage = self._properties.get(PR_INTERNET_CPID)
            return raw.decode(
                codec_name(codepage) if codepage else self._codec, errors='replace'
            )
        raw = self._read(self._path, PR_RTF_COMPRESSED, PT_BINARY)
        if not raw:
            return None
        return extract_html(decompress(raw))

    def _add_attachment(self, message: EmailMessage, path: str) -> None:
        """Attach the content of one attachment storage to the message."""
        properties = self._read_properties(path, CHILD_HEADER_SIZE)
        filename = (
            self._string(PR_ATTACH_LONG_FILENAME, path)
            or self._string(PR_ATTACH_FILENAME, path)
            or self._string(PR_DISPLAY_NAME, path)
            or 'attachment'
        )
        embedded = f'{path}/__substg1.0_{PR_ATTACH_DATA:04X}{PT_OBJECT:04X}'
        if properties.get(PR_ATTACH_METHOD) == ATTACH_EMBEDDED_MSG:
            if self._compound.is_storage(embedded):
                nested = OutlookMessage(
                    self._compound,
                    embedded,
                    EMBEDDED_HEADER_SIZE,
                )
                message.add_attachment(nested.to_email(), filename=filename)
            return
        data = self._read(path, PR_ATTACH_DATA, PT_BINARY) or b''
        mimetype = self._string(PR_ATTACH_MIME_TAG, path).lower()
        maintype, _sep, subtype = mimetype.partition('/')
        if not (maintype and subtype) or maintype == 'multipart':
            maintype, subtype = 'application', 'octet-stream'
        cid = self._string(PR_ATTACH_CONTENT_ID, path)
        message.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
            disposition='inline' if cid else 'attachment',
            cid=f'<{cid}>' if cid else None,
        )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def to_email(self) -> EmailMessage:
        """Build an email message with the headers, bodies and attachments."""
        message = EmailMessage()
        headers = {
            'From': self._sender(),
            **{key: ', '.join(values) for key, values in self._recipients().items()},
            'Subject': self._string(PR_SUBJECT),
        }
        for key, value in headers.items():
            if value:
                message[key] = value.replace('\r', ' ').replace('\n', ' ')
        if date := self._date():
            message['Date'] = format_datetime(date)
        text = self._string(PR_BODY)
        html = self._html()
        if html:
            message.set_content(text or '')
            message.add_alternative(html, subtype='html')
        else:
            message.set_content(text or '')
        for path in self._children('__attach_version1.0_#'):
            self._add_attachment(message, path)
        return message
