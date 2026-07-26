from __future__ import annotations

from odoo import models
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMailMessage(TransactionCase):
    """Verify the mail message display content computation."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Partner'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _create_message(self, **values) -> models.BaseModel:
        """Create a message on the fixture partner with the given values."""
        return self.env['mail.message'].create(
            {
                'model': 'res.partner',
                'res_id': self.partner.id,
                'message_type': 'comment',
                **values,
            }
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_display_content_joins_subject_and_preview(self):
        message = self._create_message(subject='Subject', body='<p>Body</p>')
        self.assertEqual(message.display_content, 'Subject | Body')

    def test_display_content_without_a_subject(self):
        message = self._create_message(body='<p>Body only</p>')
        self.assertEqual(message.display_content, 'Body only')

    def test_display_content_without_a_body(self):
        message = self._create_message(subject='Subject only')
        self.assertEqual(message.display_content, 'Subject only')

    def test_display_content_without_subject_and_body(self):
        message = self._create_message()
        self.assertFalse(message.display_content)

    def test_display_content_is_shortened(self):
        subject = 'Order confirmation for the annual maintenance contract'
        body = 'Please find attached the signed document for your records today'
        message = self._create_message(subject=subject, body=f'<p>{body}</p>')
        self.assertLessEqual(len(message.display_content), 100)
        self.assertTrue(message.display_content.startswith('Order confirmation'))
        self.assertTrue(message.display_content.endswith('[...]'))

    def test_display_content_collapses_whitespace(self):
        message = self._create_message(
            subject='Spaced    out',
            body='<p>Multi\n   line</p>',
        )
        self.assertEqual(message.display_content, 'Spaced out | Multi line')

    def test_display_content_keeps_unicode(self):
        message = self._create_message(subject='Änderung 变更', body='<p>Text</p>')
        self.assertEqual(message.display_content, 'Änderung 变更 | Text')

    def test_display_content_follows_a_subject_change(self):
        message = self._create_message(subject='Before', body='<p>Body</p>')
        message.write({'subject': 'After'})
        self.assertEqual(message.display_content, 'After | Body')

    def test_display_content_is_stored(self):
        message = self._create_message(subject='Stored', body='<p>Body</p>')
        self.env.flush_all()
        self.env.cr.execute(
            'SELECT display_content FROM mail_message WHERE id = %s', [message.id]
        )
        self.assertEqual(self.env.cr.fetchone()[0], 'Stored | Body')
