import odoo.tests

from odoo.tests.common import new_test_user
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestCSVPreview(odoo.tests.HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
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
        cls.csv_attachment = cls.env['ir.attachment'].create({
            'name': 'test_data.csv',
            'raw': b'Name,Email,Age\nAlice,alice@example.com,30\nBob,bob@example.com,25\n',
            'mimetype': 'text/csv',
            'public': True,
        })
        cls.tsv_attachment = cls.env['ir.attachment'].create({
            'name': 'test_data.tsv',
            'raw': b'Name\tEmail\tAge\nAlice\talice@example.com\t30\n',
            'mimetype': 'text/tab-separated-values',
            'public': True,
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_csv_preview_returns_html_table(self):
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        response = self.url_open(
            f'/muk_web_preview/preview/csv/{self.csv_attachment.id}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('<table>', response.text)
        self.assertIn('Alice', response.text)
        self.assertIn('alice@example.com', response.text)
        self.assertIn('<th>', response.text)

    def test_csv_preview_escapes_html(self):
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        attachment = self.env['ir.attachment'].create({
            'name': 'xss_test.csv',
            'raw': b'Name,Value\n<script>alert(1)</script>,safe\n',
            'mimetype': 'text/csv',
            'public': True,
        })
        response = self.url_open(
            f'/muk_web_preview/preview/csv/{attachment.id}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<script>', response.text)
        self.assertIn('&lt;script&gt;', response.text)

    def test_tsv_preview(self):
        self.authenticate(self.test_user.login, 'csv_preview_test_user')
        response = self.url_open(
            f'/muk_web_preview/preview/csv/{self.tsv_attachment.id}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('Alice', response.text)

    def test_csv_preview_unauthenticated(self):
        response = self.url_open(
            f'/muk_web_preview/preview/csv/{self.csv_attachment.id}',
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (303, 403))
