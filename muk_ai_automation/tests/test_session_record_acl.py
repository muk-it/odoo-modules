from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'muk_ai_automation')
class TestSessionRecordAcl(TransactionCase):
    """Test that linked-record access decides which foreign sessions are found."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up foreign sessions linked to a visible, a hidden, and a gone record."""
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
        cls.visible = cls.env['res.partner'].create({'name': 'Visible Partner'})
        cls.hidden = cls.env['res.partner'].create({'name': 'Hidden Partner'})
        cls.env['ir.rule'].create(
            {
                'name': 'Hide one partner from internal users',
                'model_id': cls.env['ir.model']._get_id('res.partner'),
                'domain_force': "[('id', '!=', %d)]" % cls.hidden.id,
                'groups': [(4, cls.env.ref('base.group_user').id)],
            }
        )
        gone = cls.env['res.partner'].create({'name': 'Gone Partner'})
        cls.visible_session = cls._make_session(cls.visible.id)
        cls.hidden_session = cls._make_session(cls.hidden.id)
        cls.orphan_session = cls._make_session(gone.id)
        gone.unlink()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _make_session(cls, partner_id: int) -> models.BaseModel:
        """Create an owner-held session linked to the given partner."""
        return (
            cls.env['muk_ai.session']
            .with_user(cls.owner)
            .create(
                {
                    'name': 'Linked Session %d' % partner_id,
                    'res_model': 'res.partner',
                    'res_id': partner_id,
                }
            )
        )

    def _search_as_reader(self, session: models.BaseModel) -> models.BaseModel:
        """Search ``session`` by id as the non-owner reader."""
        return (
            self.env['muk_ai.session']
            .with_user(self.reader)
            .search([('id', '=', session.id)])
        )

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_reader_finds_a_session_on_a_readable_record(self):
        found = self._search_as_reader(self.visible_session)
        self.assertEqual(found.ids, [self.visible_session.id])

    def test_reader_cannot_find_a_session_on_an_unreadable_record(self):
        self.assertFalse(self._search_as_reader(self.hidden_session))
        with self.assertRaises(AccessError):
            self.hidden_session.with_user(self.reader).read(['name'])

    def test_search_survives_a_session_whose_record_was_deleted(self):
        self.assertFalse(self._search_as_reader(self.orphan_session))
        found = self.env['muk_ai.session'].with_user(self.reader).search([])
        self.assertNotIn(self.orphan_session.id, found.ids)
        self.assertIn(self.visible_session.id, found.ids)
