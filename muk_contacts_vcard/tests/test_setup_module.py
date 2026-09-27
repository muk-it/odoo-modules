from __future__ import annotations

from odoo.tests import TransactionCase

from odoo.addons.muk_contacts_vcard import _setup_module


class TestSetupModule(TransactionCase):
    """Covers the name split and mobile restore performed by the install hook."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _log_upgrade_note(self, partner, body: str) -> None:
        """Store ``body`` verbatim as a chatter note, as the version upgrade did."""
        message = self.env['mail.message'].create(
            {
                'model': 'res.partner',
                'res_id': partner.id,
                'message_type': 'notification',
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE mail_message SET body = %s WHERE id = %s', (body, message.id)
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_setup_module_splits_archived_partners(self):
        partner = self.env['res.partner'].create({'name': 'John Smith'})
        partner.flush_recordset()
        self.env.cr.execute(
            """
                UPDATE res_partner
                SET active = FALSE,
                    firstname = NULL,
                    middlename = NULL,
                    lastname = NULL,
                    name = 'John Smith'
                WHERE id = %s
            """,
            (partner.id,),
        )
        partner.invalidate_recordset()
        _setup_module(self.env)
        self.assertEqual(partner.firstname, 'John')
        self.assertEqual(partner.lastname, 'Smith')
        self.assertEqual(partner.name, 'John Smith')

    def test_setup_module_posts_no_tracking_messages(self):
        partner = self.env['res.partner'].create({'name': 'Jane Doe'})
        partner.flush_recordset()
        self.env.cr.execute(
            """
                UPDATE res_partner
                SET firstname = NULL,
                    middlename = NULL,
                    lastname = NULL
                WHERE id = %s
            """,
            (partner.id,),
        )
        self.env.cr.precommit.clear()
        partner.invalidate_recordset()
        messages = partner.message_ids
        _setup_module(self.env)
        self.env.cr.precommit.run()
        partner.invalidate_recordset()
        self.assertEqual(partner.lastname, 'Doe')
        self.assertEqual(partner.message_ids, messages)

    def test_setup_module_restores_the_mobile_from_upgrade_notes(self):
        cases = [
            ({'phone': '+43 1 2345678'}, '+43 664 9876543'),
            ({'phone': '+43 664 9876543'}, False),
            ({'phone2': '+43 664 9876543'}, False),
            ({'mobile': '+43 664 1111111'}, '+43 664 1111111'),
        ]
        for vals, mobile in cases:
            with self.subTest(vals=vals):
                partner = self.env['res.partner'].create({'name': 'Upgraded', **vals})
                self._log_upgrade_note(partner, 'Previous Mobile: +43 664 0000000')
                self._log_upgrade_note(partner, 'Previous Mobile: +43 664 9876543')
                _setup_module(self.env)
                partner.invalidate_recordset(['mobile'])
                self.assertEqual(partner.mobile, mobile)
