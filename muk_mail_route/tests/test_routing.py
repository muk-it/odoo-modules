from odoo.tests import tagged
from odoo.tools.misc import file_open

from odoo.addons.mail.tests.common import MailCommon


@tagged('post_install', '-at_install')
class TestMailRouting(MailCommon):
    """Test that unroutable mails land in the failure container."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_failed_routing(self):
        container = self.env['mail.thread']._get_failed_route_container()
        with file_open('muk_mail_route/tests/data/no_route.eml', 'rb') as mail:
            record_id = self.env['mail.thread'].message_process(False, mail.read())
        self.assertEqual(container.id, record_id)

    def test_failed_catchall(self):
        self.env['mail.alias.domain'].create(
            {
                'catchall_alias': 'catchall',
                'name': 'catchall',
            }
        )
        container = self.env['mail.thread']._get_failed_route_container()
        with file_open('muk_mail_route/tests/data/catchall.eml', 'rb') as mail:
            record_id = self.env['mail.thread'].message_process(False, mail.read())
        self.assertEqual(container.id, record_id)
