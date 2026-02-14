from odoo.tests.common import TransactionCase
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestMailMessage(TransactionCase):

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_display_content(self):
        partner = self.env['res.partner'].create({
            'name': 'Partner'
        })
        message = self.env['mail.message'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'message_type': 'comment',
            'subject': 'Subject',
            'body': '<p>Body</p>',
        })
        self.assertIn('Subject', message.display_content)
