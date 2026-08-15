from __future__ import annotations

from requests import Response

import odoo.tests
from odoo import models
from odoo.tests.common import new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestCSVPreview(odoo.tests.HttpCase):
    """Test the CSV/TSV attachment preview controller."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.test_user = new_test_user(
            cls.env,
            login='csv_preview_test_user',
            password='csv_preview_test_user',
            groups='base.group_user',
            context={
                'mail_create_nosubscribe': True,
                'mail_notrack': True,
                'no_reset_password': True,
            },
        )
        cls.csv_attachment = cls._create_attachment(
            'test_data.csv',
            b'Name,Email,Age\nAlice,alice@example.com,30\nBob,bob@example.com,25\n',
            'text/csv',
        )
        cls.tsv_attachment = cls._create_attachment(
            'test_data.tsv',
            b'Name\tEmail\tAge\nAlice\talice@example.com\t30\n',
            'text/tab-separated-values',
        )
        cls.env['ir.model.data'].create(
            {
                'name': 'test_csv_preview_attachment',
                'module': 'muk_web_preview',
                'model': 'ir.attachment',
                'res_id': cls.csv_attachment.id,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _create_attachment(
        cls, name: str, raw: bytes, mimetype: str = 'text/csv'
    ) -> models.BaseModel:
        """Create a public attachment holding the given raw payload."""
        return cls.env['ir.attachment'].create(
            {
                'name': name,
                'raw': raw,
                'mimetype': mimetype,
                'public': True,
            }
        )

    def _preview(self, attachment: models.BaseModel) -> Response:
        """Authenticate and request the CSV preview for an attachment."""
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        return self.url_open(f'/muk_web_preview/preview/csv/{attachment.id}')

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_csv_preview_returns_html_table(self):
        response = self._preview(self.csv_attachment)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<table>', response.text)
        self.assertIn('<th>Name</th>', response.text)
        self.assertIn('<td>Alice</td>', response.text)
        self.assertIn('<td>alice@example.com</td>', response.text)

    def test_csv_preview_only_the_first_row_is_a_header(self):
        response = self._preview(self.csv_attachment)
        self.assertEqual(response.text.count('<th>'), 3)
        self.assertEqual(response.text.count('<tr>'), 3)

    def test_csv_preview_escapes_html(self):
        attachment = self._create_attachment(
            'xss_test.csv',
            b'Name,Value\n<script>alert(1)</script>,safe\n',
        )
        response = self._preview(attachment)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script>', response.text)
        self.assertIn('&lt;script&gt;', response.text)

    def test_tsv_preview(self):
        response = self._preview(self.tsv_attachment)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<td>Alice</td>', response.text)
        self.assertIn('<th>Email</th>', response.text)

    def test_semicolon_delimiter_is_sniffed(self):
        attachment = self._create_attachment(
            'semicolon.csv',
            b'Name;Email\nAlice;alice@example.com\nBob;bob@example.com\n',
        )
        response = self._preview(attachment)
        self.assertIn('<th>Name</th>', response.text)
        self.assertIn('<td>alice@example.com</td>', response.text)

    def test_latin1_payload_is_decoded(self):
        attachment = self._create_attachment(
            'latin1.csv',
            b'Name,City\nRen\xe9,Z\xfcrich\n',
        )
        response = self._preview(attachment)
        self.assertEqual(response.status_code, 200)
        self.assertIn('René', response.text)
        self.assertIn('Zürich', response.text)

    def test_cp1252_payload_is_decoded(self):
        attachment = self._create_attachment(
            'cp1252.csv',
            'Name,Price\nAlice,12€\nBob,9–x\n'.encode('cp1252'),
        )
        response = self._preview(attachment)
        self.assertEqual(response.status_code, 200)
        self.assertIn('12€', response.text)
        self.assertIn('9–x', response.text)

    def test_utf8_bom_is_stripped(self):
        attachment = self._create_attachment(
            'bom.csv',
            b'\xef\xbb\xbfName,City\nAlice,Vienna\n',
        )
        response = self._preview(attachment)
        self.assertIn('<th>Name</th>', response.text)
        self.assertNotIn('﻿', response.text)

    def test_empty_file_renders_an_empty_table(self):
        attachment = self._create_attachment('empty.csv', b'')
        response = self._preview(attachment)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<table></table>', response.text)
        self.assertNotIn('class="muk_truncated"', response.text)

    def test_row_count_is_capped(self):
        rows = b'Name\n' + b''.join(b'row%d\n' % index for index in range(600))
        attachment = self._create_attachment('many_rows.csv', rows)
        response = self._preview(attachment)
        self.assertIn('Showing first 500 rows', response.text)
        self.assertEqual(response.text.count('<tr>'), 501)
        self.assertNotIn('<td>row599</td>', response.text)

    def test_column_count_is_capped(self):
        header = ','.join(f'c{index}' for index in range(60))
        values = ','.join(f'v{index}' for index in range(60))
        attachment = self._create_attachment(
            'many_cols.csv',
            f'{header}\n{values}\n'.encode(),
        )
        response = self._preview(attachment)
        self.assertIn('<th>c49</th>', response.text)
        self.assertNotIn('<th>c50</th>', response.text)
        self.assertIn('<th>…</th>', response.text)
        self.assertIn('<td>…</td>', response.text)

    def test_csv_preview_xmlid_route(self):
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        response = self.url_open(
            '/muk_web_preview/preview/csv/muk_web_preview.test_csv_preview_attachment',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('<td>Alice</td>', response.text)

    def test_csv_preview_model_field_route(self):
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        response = self.url_open(
            f'/muk_web_preview/preview/csv/ir.attachment/{self.csv_attachment.id}/raw',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('<td>Alice</td>', response.text)

    def test_csv_preview_unauthenticated(self):
        response = self.url_open(
            f'/muk_web_preview/preview/csv/{self.csv_attachment.id}',
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (303, 403))

    @mute_logger('odoo.http')
    def test_csv_preview_unknown_attachment(self):
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        missing_id = self.env['ir.attachment'].search([], order='id desc', limit=1).id
        response = self.url_open(
            f'/muk_web_preview/preview/csv/{missing_id + 1000}',
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 404)
