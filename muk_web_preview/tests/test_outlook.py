from __future__ import annotations

import random
import struct

from odoo.tests import BaseCase
from odoo.tools import file_open

from odoo.addons.muk_web_preview.tools.compound import (
    SIGNATURE,
    CompoundFile,
    CompoundFileError,
)
from odoo.addons.muk_web_preview.tools.outlook import OutlookMessage
from odoo.addons.muk_web_preview.tools.rtf import decompress, extract_html


def read_message(name: str) -> OutlookMessage:
    """Open one of the Outlook files of the test data folder."""
    with file_open(f'muk_web_preview/tests/data/{name}', 'rb') as file:
        return OutlookMessage.from_bytes(file.read())


def build_compound(directory: int = 2, root_type: int = 5) -> bytes:
    """Build an empty compound file whose FAT sector is listed in a DIFAT sector."""
    free = 0xFFFFFFFF
    header = SIGNATURE + bytes(16) + struct.pack('<HHHHH', 0x3E, 3, 0xFFFE, 9, 6)
    header += bytes(10) + struct.pack(
        '<9I', 1, directory, 0, 4096, 0xFFFFFFFE, 0, 0, 1, free
    )
    header += struct.pack('<108I', *[free] * 108)
    difat_sector = struct.pack('<128I', 1, *[free] * 126, 0xFFFFFFFE)
    fat = struct.pack('<128I', 0xFFFFFFFC, 0xFFFFFFFD, 0xFFFFFFFE, *[free] * 125)
    root = 'Root Entry'.encode('utf-16-le').ljust(64, b'\0')
    root += struct.pack('<HBB3I', 22, root_type, 1, free, free, free)
    root += bytes(36) + struct.pack('<II', 0xFFFFFFFE, 0) + bytes(4)
    return header + difat_sector + fat + root.ljust(512, b'\0')


class TestOutlook(BaseCase):
    """Test the conversion of Outlook item files to email messages."""

    def test_headers_and_bodies(self):
        cases = [
            (
                'html_body.msg',
                'Microsoft Outlook テスト メッセージ',
                'Microsoft Outlook <ku@digitaldolphins.jp>',
                'text/html',
                ('Microsoft Outlook から自動送信',),
            ),
            (
                'cjk.msg',
                'Hello +CJK',
                None,
                'text/html',
                ('你好', 'こんにちは', '안녕하세요'),
            ),
            (
                'non_unicode_cp932.msg',
                '日本語 Non Unicode タイトル',
                None,
                'text/html',
                ('日本語', '本文'),
            ),
            ('plain_text.msg', 'title', None, 'text/plain', ('body',)),
        ]
        for name, subject, sender, content_type, texts in cases:
            with self.subTest(name=name):
                message = read_message(name).to_email()
                body = message.get_body(preferencelist=('html', 'plain'))
                self.assertEqual(message['Subject'], subject)
                self.assertEqual(message['From'], sender)
                self.assertEqual(body.get_content_type(), content_type)
                for text in texts:
                    self.assertIn(text, body.get_content())

    def test_recipients_and_date(self):
        message = read_message('recipients.msg').to_email()
        self.assertEqual(message['To'], 'ToUser <to@example.com>')
        self.assertEqual(message['Cc'], 'ToCc <cc@example.com>')
        self.assertEqual(message['Bcc'], 'ToBcc <bcc@example.com>')
        self.assertEqual(message['Date'], 'Mon, 28 Sep 2020 11:28:39 +0000')

    def test_attachments(self):
        message = read_message('attach_and_inline.msg').to_email()
        attachments = {part.get_filename(): part for part in message.iter_attachments()}
        self.assertEqual(set(attachments), {'attach.png', 'image001.png'})
        inline = attachments['image001.png']
        self.assertEqual(inline['Content-ID'], '<image001.png@01D78380.EF6DC500>')
        self.assertEqual(inline.get_content_type(), 'image/png')
        self.assertTrue(inline.get_content().startswith(b'\x89PNG'))
        self.assertIn(
            'cid:image001.png@01D78380.EF6DC500',
            message.get_body(preferencelist=('html',)).get_content(),
        )

    def test_embedded_message(self):
        message = read_message('msg_in_msg.msg').to_email()
        nested = next(
            part
            for part in message.iter_attachments()
            if part.get_content_type() == 'message/rfc822'
        )
        self.assertEqual(
            nested.get_payload(0)['Subject'],
            'Microsoft Outlook テスト メッセージ',
        )

    def test_invalid_files(self):
        with file_open('muk_web_preview/tests/data/plain_text.msg', 'rb') as file:
            truncated = file.read()[:2048]
        cases = [b'', b'not an outlook file' * 40, SIGNATURE + bytes(600), truncated]
        for data in cases:
            with self.subTest(data=data[:24]), self.assertRaises(CompoundFileError):
                OutlookMessage.from_bytes(data)

    def test_compound_structure(self):
        self.assertEqual(CompoundFile(build_compound()).listdir(), [])
        for data in (build_compound(directory=200), build_compound(root_type=1)):
            with self.subTest(data=data[:80]), self.assertRaises(CompoundFileError):
                CompoundFile(data)

    def test_corrupted_files(self):
        samples = []
        for name in ('attach_and_inline.msg', 'msg_in_msg.msg', 'recipients.msg'):
            with file_open(f'muk_web_preview/tests/data/{name}', 'rb') as file:
                samples.append(file.read())
        generator = random.Random(20)
        outcomes = set()
        for _index in range(150):
            data = bytearray(generator.choice(samples))
            for _flip in range(generator.randint(1, 12)):
                data[generator.randrange(len(data))] = generator.randrange(256)
            try:
                OutlookMessage.from_bytes(bytes(data)).to_email().as_bytes()
                outcomes.add('parsed')
            except (CompoundFileError, ValueError, struct.error) as error:
                outcomes.add(type(error).__name__)
        self.assertIn('parsed', outcomes)
        self.assertIn('CompoundFileError', outcomes)

    def test_compound_paths(self):
        with file_open('muk_web_preview/tests/data/plain_text.msg', 'rb') as file:
            compound = CompoundFile(file.read())
        self.assertIn('__properties_version1.0', compound.listdir())
        self.assertIsNone(compound.read('__missing'))
        self.assertIsNone(compound.read('__recip_version1.0_#00000000'))
        self.assertTrue(compound.is_storage('__recip_version1.0_#00000000'))
        self.assertEqual(compound.listdir('__properties_version1.0'), [])
        root = compound._entries[0]
        compound._entries[root['child']]['left'] = root['child']
        self.assertIn('__properties_version1.0', compound.listdir())

    def test_rtf(self):
        raw = b'{\\rtf1\\ansi\\fromhtml1 {\\*\\htmltag <b>}x{\\*\\htmltag </b>}}'
        stored = len(raw).to_bytes(4, 'little')
        uncompressed = (
            (len(raw) + 12).to_bytes(4, 'little') + stored + b'MELA' + bytes(4) + raw
        )
        self.assertEqual(decompress(uncompressed), raw)
        self.assertEqual(extract_html(raw), '<b>x</b>')
        raw = b"{\\rtf1\\ansi\\fromhtml1 {\\*\\htmltag <p>}\\u8364?\\uc2\\u9731 ab \\u8364\\'80\\'81x\\uc1\\u-10179?\\u-8704?{\\*\\htmltag </p>}}"
        self.assertEqual(extract_html(raw), '<p>\u20ac\u2603 \u20acx\U0001f600</p>')
        truncated = (
            (16).to_bytes(4, 'little') + bytes(4) + b'LZFu' + bytes(4) + b'\x01\x00'
        )
        self.assertEqual(decompress(truncated), b'')
        self.assertIsNone(extract_html(b'{\\rtf1\\ansi\\fromtext hello}'))
        for data in (b'short', bytes(12) + b'XXXX'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decompress(data)
