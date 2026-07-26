from __future__ import annotations

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBrowserDevice(TransactionCase):
    """Verify device minting, the backing key and revocation."""

    def setUp(self) -> None:
        super().setUp()
        self.device_model = self.env['muk_ai_browser.device']
        self.key_model = self.env['muk_mcp.key']
        self.user = self.env.ref('base.user_admin')

    def test_mint_creates_working_key_and_device(self):
        key, raw = self.device_model._mint(
            self.user.id,
            'Laptop',
            scope='write',
            user_agent='Mozilla/5.0',
            ip_address='10.0.0.1',
        )
        self.assertEqual(self.key_model.authenticate(raw), key)
        device = self.device_model.search([('key_id', '=', key.id)], limit=1)
        self.assertTrue(device)
        self.assertEqual(device.name, 'Laptop')
        self.assertEqual(device.user_id, self.user)
        self.assertEqual(device.user_agent, 'Mozilla/5.0')
        self.assertEqual(device.last_seen_ip, '10.0.0.1')
        self.assertEqual(device.key_prefix, raw[:8])
        self.assertTrue(device.active)

    def test_action_revoke_deactivates_key(self):
        key, raw = self.device_model._mint(self.user.id, 'Phone')
        device = self.device_model.search([('key_id', '=', key.id)], limit=1)
        device.action_revoke()
        key.invalidate_recordset(['active'])
        self.assertFalse(key.active)
        self.assertIsNone(self.key_model.authenticate(raw))
        device.invalidate_recordset(['active'])
        self.assertFalse(device.active)
