import secrets

from odoo.tests import common


class TestMcpKey(common.TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key_model = cls.env['muk_mcp.key']
        cls.raw_token = secrets.token_urlsafe(32)
        cls.key = cls.key_model.create({
            'name': 'Test Key',
            'user_id': cls.env.user.id,
            'key_hash': cls.key_model._hash_key(cls.raw_token),
            'key_prefix': cls.raw_token[:8],
            'rate_limit': 10,
        })

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_authenticate_valid_key(self):
        found = self.key_model.authenticate(self.raw_token)
        self.assertEqual(found.id, self.key.id)

    def test_authenticate_invalid_key(self):
        found = self.key_model.authenticate('bogus-token-that-does-not-exist')
        self.assertIsNone(found)

    def test_authenticate_updates_last_used(self):
        self.assertFalse(self.key.last_used)
        self.key_model.authenticate(self.raw_token)
        self.key.invalidate_recordset()
        self.assertTrue(self.key.last_used)

    def test_model_access_no_scopes_allows_all(self):
        self.assertFalse(self.key.scope_ids)
        self.assertTrue(self.key._check_model_access('res.partner', 'read'))
        self.assertTrue(self.key._check_model_access('sale.order', 'write'))

    def test_model_access_with_scopes(self):
        partner_model = self.env['ir.model']._get('res.partner')
        self.env['muk_mcp.scope'].create({
            'key_id': self.key.id,
            'model_id': partner_model.id,
            'perm_read': True,
            'perm_write': False,
            'perm_create': False,
            'perm_unlink': False,
        })
        self.key.invalidate_recordset()
        self.assertTrue(self.key._check_model_access('res.partner', 'read'))
        self.assertFalse(self.key._check_model_access('res.partner', 'write'))
        self.assertFalse(self.key._check_model_access('res.partner', 'create'))
        self.assertFalse(self.key._check_model_access('res.partner', 'unlink'))
        self.assertFalse(self.key._check_model_access('sale.order', 'read'))

    def test_rate_limit(self):
        for _i in range(10):
            self.assertTrue(self.key._check_rate_limit())
        self.assertFalse(self.key._check_rate_limit())
