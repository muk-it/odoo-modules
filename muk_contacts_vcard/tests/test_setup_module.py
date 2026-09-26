from odoo.tests import TransactionCase

from odoo.addons.muk_contacts_vcard import _setup_module


class TestSetupModule(TransactionCase):
    """Covers the one-time name split performed by the install hook."""

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
