from odoo.exceptions import AccessError
from odoo.tests import common


class TestMCPAccessModel(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.access_model = cls.env['muk_mcp_access.model']
        cls.mixin = cls.env['muk_mcp.mixin']
        cls.partner_model = cls.env.ref('base.model_res_partner')
        cls.user_model = cls.env.ref('base.model_res_users')

    # ----------------------------------------------------------
    # Tests: allowlist inactive (empty)
    # ----------------------------------------------------------

    def test_empty_allowlist_allows_everything(self):
        self.assertTrue(
            self.access_model._is_model_allowed('res.partner'),
        )
        self.assertTrue(
            self.access_model._is_model_allowed('res.users', 'write'),
        )

    def test_empty_allowlist_returns_none(self):
        self.assertIsNone(self.access_model._get_allowed_model_names())

    def test_resolve_model_passes_with_empty_allowlist(self):
        result = self.mixin._resolve_model('res.partner')
        self.assertEqual(result._name, 'res.partner')

    def test_list_models_unfiltered_with_empty_allowlist(self):
        result = self.mixin._mcp_list_models(search='res.partner')
        names = [m['model'] for m in result]
        self.assertIn('res.partner', names)

    # ----------------------------------------------------------
    # Tests: allowlist active (non-empty)
    # ----------------------------------------------------------

    def test_allowed_model_passes(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
            'allow_write': False,
        })
        self.assertTrue(
            self.access_model._is_model_allowed('res.partner', 'read'),
        )

    def test_unlisted_model_blocked(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
        })
        self.assertFalse(
            self.access_model._is_model_allowed('res.users', 'read'),
        )

    def test_write_denied_when_read_only(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
            'allow_write': False,
        })
        self.assertFalse(
            self.access_model._is_model_allowed('res.partner', 'write'),
        )

    def test_write_allowed_when_enabled(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
            'allow_write': True,
        })
        self.assertTrue(
            self.access_model._is_model_allowed('res.partner', 'write'),
        )

    def test_resolve_model_blocks_unlisted(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
        })
        with self.assertRaises(AccessError):
            self.mixin._resolve_model('res.users')

    def test_resolve_model_allows_listed(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
        })
        result = self.mixin._resolve_model('res.partner')
        self.assertEqual(result._name, 'res.partner')

    def test_list_models_filters_to_allowlist(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
        })
        result = self.mixin._mcp_list_models(search='res.')
        names = [m['model'] for m in result]
        self.assertIn('res.partner', names)
        for name in names:
            self.assertEqual(name, 'res.partner')

    def test_get_allowed_model_names_read(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
            'allow_write': False,
        })
        self.access_model.create({
            'model_id': self.user_model.id,
            'allow_read': True,
            'allow_write': True,
        })
        read_models = self.access_model._get_allowed_model_names('read')
        self.assertEqual(read_models, {'res.partner', 'res.users'})

    def test_get_allowed_model_names_write(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'allow_read': True,
            'allow_write': False,
        })
        self.access_model.create({
            'model_id': self.user_model.id,
            'allow_read': True,
            'allow_write': True,
        })
        write_models = self.access_model._get_allowed_model_names('write')
        self.assertEqual(write_models, {'res.users'})

    # ----------------------------------------------------------
    # Tests: constraints
    # ----------------------------------------------------------

    def test_duplicate_blocked_by_wizard(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
        })
        wizard = self.env['muk_mcp_access.model.selection'].create({
            'model_ids': [(6, 0, [self.partner_model.id])],
        })
        wizard.action_enable_models()
        self.assertEqual(
            self.access_model.search_count([
                ('model_id', '=', self.partner_model.id),
            ]),
            1,
        )

    def test_no_permissions_raises(self):
        with self.assertRaises(Exception):
            self.access_model.create({
                'model_id': self.partner_model.id,
                'allow_read': False,
                'allow_write': False,
            })

    # ----------------------------------------------------------
    # Tests: archived entries
    # ----------------------------------------------------------

    def test_archived_entry_not_counted(self):
        self.access_model.create({
            'model_id': self.partner_model.id,
            'active': False,
        })
        self.assertFalse(self.access_model._is_active())
        self.assertTrue(
            self.access_model._is_model_allowed('anything'),
        )
