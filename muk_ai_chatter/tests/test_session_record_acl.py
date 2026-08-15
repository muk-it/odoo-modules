from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_chatter')
class TestSessionRecordAcl(TransactionCase):
    """Test that a linked session stays private to the user who ran it."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up a foreign session linked to a record the reader may read."""
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env,
            login='acl_session_owner',
            groups='base.group_user',
        )
        cls.reader = new_test_user(
            cls.env,
            login='acl_session_reader',
            groups='base.group_user',
        )
        cls.partner = cls.env['res.partner'].create({'name': 'Visible Partner'})
        cls.session = (
            cls.env['muk_ai.session']
            .with_user(cls.owner)
            .create(
                {
                    'name': 'Linked Session',
                    'res_model': 'res.partner',
                    'res_id': cls.partner.id,
                }
            )
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_reading_the_record_does_not_find_the_session_on_it(self):
        self.assertTrue(self.partner.with_user(self.reader).has_access('read'))
        found = (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search([('id', '=', self.session.id)])
        )
        self.assertFalse(found)

    def test_reading_the_record_does_not_open_the_session_on_it(self):
        with self.assertRaises(AccessError):
            self.session.with_user(self.reader).read(['name'])

    def test_owner_still_finds_their_own_session(self):
        found = (
            self.env['muk_ai.session']
            .with_user(self.owner)
            .search([('id', '=', self.session.id)])
        )
        self.assertEqual(found.ids, [self.session.id])

    def test_an_access_rights_admin_is_shown_no_foreign_session_either(self):
        manager = new_test_user(
            self.env,
            login='acl_rights_manager',
            groups='base.group_user,base.group_erp_manager',
        )
        self.assertFalse(manager.has_group('base.group_system'))
        self.assertFalse(
            self.env['muk_ai.session']
            .with_user(manager)
            .search([('id', '=', self.session.id)])
        )
        summary = self.partner.with_user(manager).get_ai_sessions_summary()
        entry = summary[self.partner.id]
        self.assertEqual(entry['entries'], [])
        self.assertEqual(entry['total'], 0)

    def test_chatter_lists_only_the_sessions_the_caller_owns(self):
        summary = self.partner.with_user(self.reader).get_ai_sessions_summary()
        entry = summary[self.partner.id]
        self.assertEqual(entry['entries'], [])
        self.assertEqual(entry['total'], 0)
        owned = self.partner.with_user(self.owner).get_ai_sessions_summary()
        self.assertEqual(
            [row['id'] for row in owned[self.partner.id]['entries']],
            [self.session.id],
        )
        self.assertEqual(owned[self.partner.id]['total'], 1)
