from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_contacts_vcard import _setup_module


@tagged('post_install', '-at_install')
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
