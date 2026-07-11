import json

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestPairing(HttpCase):
    """Verify pairing-code minting/consumption and device-key lifecycle."""

    def setUp(self):
        super().setUp()
        self.pairing = self.env['muk_mcp.pairing']
        self.key_model = self.env['muk_mcp.key']
        self.device_model = self.env['muk_ai_browser.device']
        self.user = self.env.ref('base.user_admin')

    def test_mint_and_consume_single_use(self):
        code = self.pairing._mint_code(self.user.id, 'Device A', 'write')
        consumed = self.pairing._consume(code)
        self.assertEqual(consumed['user_id'], self.user.id)
        self.assertEqual(consumed['scope'], 'write')
        self.assertEqual(consumed['device_label'], 'Device A')
        self.assertIsNone(self.pairing._consume(code))

    def test_consume_unknown_code_returns_none(self):
        self.assertIsNone(self.pairing._consume('nope'))
        self.assertIsNone(self.pairing._consume(None))

    def test_consume_expired_returns_none(self):
        code = self.pairing._mint_code(self.user.id, 'Device B', 'read')
        record = self.pairing.search([('code_prefix', '=', code[:8])], limit=1)
        record.expires_at = fields.Datetime.subtract(fields.Datetime.now(), minutes=5)
        self.assertIsNone(self.pairing._consume(code))

    def test_mint_device_key_authenticates(self):
        key, raw = self.device_model._mint(self.user.id, 'Device C', 'write')
        device = self.device_model.search([('key_id', '=', key.id)], limit=1)
        self.assertTrue(device)
        self.assertEqual(key.user_id, self.user)
        self.assertEqual(key.key_prefix, raw[:8])
        self.assertEqual(self.key_model.authenticate(raw), key)

    def _db_url(self, path: str) -> str:
        """Return a browser route URL with the current database selected.

        The extension is a session-less client, so it selects its database via
        the ``?db=`` selector; this keeps the routes reachable on a multi-db
        host where an anonymous request cannot otherwise resolve one.
        """
        return f'{path}?db={self.env.cr.dbname}'

    def test_whoami_then_unpair_revokes(self):
        key, raw = self.device_model._mint(self.user.id, 'Device D', 'write')
        headers = {'Authorization': f'Bearer {raw}'}
        whoami = self.url_open(self._db_url('/muk_ai_browser/whoami'), headers=headers)
        self.assertEqual(whoami.status_code, 200)
        self.assertEqual(whoami.json()['user'], self.user.id)
        unpair = self.url_open(
            self._db_url('/muk_ai_browser/unpair'),
            data=b'{}',
            headers={**headers, 'Content-Type': 'application/json'},
        )
        self.assertEqual(unpair.status_code, 200)
        key.invalidate_recordset(['active'])
        self.assertFalse(key.active)
        self.assertIsNone(self.key_model.authenticate(raw))

    def test_pair_endpoint_mints_key_once(self):
        code = self.pairing._mint_code(self.user.id, 'Device E', 'write')
        body = json.dumps({'pairing_code': code}).encode()
        headers = {'Content-Type': 'application/json'}
        url = self._db_url('/muk_ai_browser/pair')
        response = self.url_open(url, data=body, headers=headers)
        result = response.json()
        self.assertTrue(result['api_key'])
        self.assertEqual(result['scope'], 'write')
        self.assertEqual(
            self.key_model.authenticate(result['api_key']).id,
            result['device_id'],
        )
        replay = self.url_open(url, data=body, headers=headers)
        self.assertEqual(replay.json().get('error'), 'invalid_or_expired_code')
