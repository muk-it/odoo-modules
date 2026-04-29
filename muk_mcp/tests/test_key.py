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

    def test_scope_default_is_write(self):
        self.assertEqual(self.key.scope, 'write')

    def test_rate_limit(self):
        for _i in range(10):
            self.assertTrue(self.key._check_rate_limit())
        self.assertFalse(self.key._check_rate_limit())
