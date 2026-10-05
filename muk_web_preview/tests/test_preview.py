from __future__ import annotations

import html
import re
from email.message import EmailMessage
from unittest.mock import patch

from requests import Response

from odoo.tests import HttpCase
from odoo.tools import file_open, mute_logger

from odoo.addons.mail.controllers.attachment import AttachmentController


class TestPreview(HttpCase):
    """Test the table and email previews of the attachment text route."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _preview(
        self, name: str, raw: bytes, mimetype: str, query: str = ''
    ) -> Response:
        """Store an attachment and open its preview through the public route."""
        attachment = self.env['ir.attachment'].create(
            {
                'name': name,
                'raw': raw,
                'mimetype': mimetype,
                'res_model': 'res.partner',
                'res_id': self.env.user.partner_id.id,
            }
        )
        attachment.generate_access_token()
        return self.url_open(
            f'/mail/attachment/render_text/{attachment.id}'
            f'?access_token={attachment.access_token}{query}'
        )

    def _email(self, html: str) -> bytes:
        """Build an email with an HTML body, an inline image and a file."""
        message = EmailMessage()
        message['From'] = 'Alice <alice@example.com>'
        message['To'] = 'bob@example.com'
        message['Cc'] = 'carol@example.com'
        message['Subject'] = 'Quarterly report'
        message['Date'] = 'Mon, 02 Mar 2026 10:00:00 +0000'
        message.set_content('plain body')
        message.add_alternative(html, subtype='html')
        message.get_payload()[1].add_related(
            b'\x89PNG-logo', 'image', 'png', cid='<logo@example>'
        )
        message.add_attachment(
            b'%PDF' + b'0' * 2048,
            maintype='application',
            subtype='pdf',
            filename='report.pdf',
        )
        return message.as_bytes()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_table(self):
        cases = [
            ('prices.csv', 'text/csv', b'Item;Price\nCoffee;3,50 \x80\n', '3,50 €'),
            (
                'prices.tsv',
                'text/tab-separated-values',
                b'Item\tPrice\nCoffee\t3,50 \xe2\x82\xac\n',
                '3,50 €',
            ),
            (
                'prices.csv',
                'application/octet-stream',
                b'Item,Price\nCoffee,"3,50 \xe2\x82\xac"\n',
                '3,50 €',
            ),
            ('legacy.csv', 'text/csv', b'Item;Price\nCaf\xe9\x81;1\n', 'Caf\xe9'),
            ('names.csv', 'text/csv', b'Item\nAnna\nBert\n', 'Anna'),
        ]
        for name, mimetype, raw, cell in cases:
            with self.subTest(name=name, mimetype=mimetype):
                response = self._preview(name, raw, mimetype)
                self.assertEqual(response.status_code, 200)
                self.assertIn('<th>Item</th>', response.text)
                self.assertIn(f'<td>{cell}', response.text)
                self.assertIn(
                    "default-src 'none'", response.headers['Content-Security-Policy']
                )

    def test_table_thumbnail_cut_inside_character(self):
        raw = 'Item,Price\nCoffee,3 €\nTea,2 €'.encode()
        size = raw.rindex('€'.encode()) + 1
        with patch.object(AttachmentController, 'TEXTUAL_THUMBNAIL_SIZE', size):
            response = self._preview('prices.csv', raw, 'text/csv', '&head=1')
        self.assertIn('<td>3 €</td>', response.text)
        self.assertIn('<td>Tea</td>', response.text)

    def test_table_limits(self):
        raw = '\n'.join(f'{row},' + ','.join(['x'] * 60) for row in range(600)).encode()
        response = self._preview('big.csv', raw, 'text/csv')
        self.assertIn('Only the first', response.text)
        self.assertIn('<td>499</td>', response.text)
        self.assertNotIn('<td>500</td>', response.text)
        self.assertEqual(response.text.count('<th>'), 50)
        thumbnail = self._preview('big.csv', raw, 'text/csv', '&head=1')
        self.assertIn('mk_preview_thumbnail', thumbnail.text)
        self.assertIn('<td>19</td>', thumbnail.text)
        self.assertNotIn('<td>20</td>', thumbnail.text)
        self.assertNotIn('Only the first', thumbnail.text)

    def test_email(self):
        html = (
            '<p>Hello <a href="https://example.com/offer">offer</a></p>'
            '<img src="cid:logo@example"><script>alert(1)</script>'
        )
        response = self._preview('report.eml', self._email(html), 'message/rfc822')
        self.assertEqual(response.status_code, 200)
        for text in (
            'Quarterly report',
            'Alice &lt;alice@example.com&gt;',
            'bob@example.com',
            'carol@example.com',
            'offer (https://example.com/offer)',
            'src="data:image/png;base64,iVBORy1sb2dv"',
            'report.pdf',
            '2.00 Kb',
        ):
            self.assertIn(text, response.text)
        self.assertNotIn('<script', response.text)
        self.assertNotIn('<a href="https://example.com', response.text)
        self.assertNotIn('mk_preview_banner', response.text)

    def test_email_remote_images(self):
        raw = self._email('<p>Hi</p><img src="https://tracker.example/pixel.gif">')
        response = self._preview('remote.eml', raw, 'message/rfc822')
        self.assertIn('Show remote images', response.text)
        self.assertIn('data-src="https://tracker.example/pixel.gif"', response.text)
        self.assertNotIn(' src="https://tracker.example', response.text)
        self.assertNotIn('https:', response.headers['Content-Security-Policy'])
        allowed = self._preview('remote.eml', raw, 'message/rfc822', '&remote_images=1')
        self.assertIn('src="https://tracker.example/pixel.gif"', allowed.text)
        self.assertNotIn('Show remote images', allowed.text)
        self.assertIn(
            "img-src 'self' data: https: http:",
            allowed.headers['Content-Security-Policy'],
        )
        thumbnail = self._preview(
            'remote.eml', raw, 'message/rfc822', '&head=1&remote_images=1'
        )
        self.assertNotIn('Show remote images', thumbnail.text)
        self.assertNotIn('https:', thumbnail.headers['Content-Security-Policy'])

    def test_email_remote_images_keep_reader_locale(self):
        self.env['res.lang']._activate_lang('de_DE')
        self.env['ir.module.module']._load_module_terms(['muk_web_preview'], ['de_DE'])
        self.env.ref('base.user_admin').write({'tz': 'Asia/Tokyo', 'lang': 'de_DE'})
        self.authenticate('admin', 'admin')
        raw = self._email('<p>Hi</p><img src="https://tracker.example/pixel.gif">')
        response = self._preview('remote.eml', raw, 'message/rfc822')
        self.assertIn('19:00:00', response.text)
        link = html.unescape(
            re.search(r'href="([^"]*remote_images=1[^"]*)"', response.text)[1]
        )
        self.authenticate(None, None)
        remote = self.url_open(link)
        self.assertIn('19:00:00', remote.text)
        self.assertIn('<th>Von</th>', remote.text)

    def test_email_plain_text(self):
        message = EmailMessage()
        message['Subject'] = 'Note'
        message.set_content('line <one>\nline two')
        response = self._preview('note.eml', message.as_bytes(), 'message/rfc822')
        self.assertIn('<pre>line &lt;one&gt;\nline two', response.text)

    def test_email_edge_cases(self):
        forward = EmailMessage()
        forward['Subject'] = 'Original offer'
        forward.set_content('original')
        wrapper = EmailMessage()
        wrapper['Subject'] = 'Fwd'
        wrapper['Date'] = 'Mon, 02 Mar 2026 10:00:00 -0000'
        wrapper.set_content('<p>see <img src="cid:missing"></p>', subtype='html')
        wrapper.add_attachment(forward)
        cases = [
            (wrapper.as_bytes(), ['Original offer', 'src="cid:missing"', '2026']),
            (
                b'Subject: Odd\r\nDate: yesterday\r\n'
                b'Content-Type: text/plain; charset="x-unknown"\r\n\r\nHello\r\n',
                ['<pre>Hello', 'yesterday'],
            ),
            (
                b'Subject: Scan\r\nContent-Type: application/pdf\r\n\r\n%PDF',
                ['Scan'],
            ),
            (b'Subject: Empty\r\nContent-Type: text/html\r\n\r\n \r\n', ['Empty']),
        ]
        for raw, texts in cases:
            with self.subTest(texts=texts):
                response = self._preview('edge.eml', raw, 'message/rfc822')
                self.assertEqual(response.status_code, 200)
                for text in texts:
                    self.assertIn(text, response.text)

    def test_outlook(self):
        with file_open(
            'muk_web_preview/tests/data/attach_and_inline.msg', 'rb'
        ) as file:
            raw = file.read()
        response = self._preview('inline.msg', raw, 'application/octet-stream')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Attach and inline', response.text)
        self.assertIn('src="data:image/png;base64,', response.text)
        self.assertIn('attach.png', response.text)
        self.assertNotIn('image001.png', response.text)
        with mute_logger('odoo.http'):
            broken = self._preview(
                'broken.msg', b'not outlook', 'application/vnd.ms-outlook'
            )
        self.assertEqual(broken.status_code, 415)

    def test_source_code(self):
        response = self._preview('script.py', b'print("<hi>")', 'text/x-python')
        self.assertEqual(response.status_code, 200)
        self.assertIn('print(&#34;&lt;hi&gt;&#34;)', response.text)
