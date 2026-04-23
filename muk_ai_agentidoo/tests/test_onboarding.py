from unittest.mock import patch

import requests

from odoo.exceptions import UserError, ValidationError

from .common import AgentidooTestCommon


class TestAgentidooOnboarding(AgentidooTestCommon):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _new_wizard(self):
        return self.env['muk_ai_agentidoo.onboarding'].create({})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_state_defaults_to_intro(self):
        wizard = self._new_wizard()
        self.assertEqual(wizard.state, 'intro')
        self.assertEqual(wizard.api_url, 'https://agentidoo.test')

    def test_intro_advances_to_api_key(self):
        wizard = self._new_wizard()
        wizard.action_next()
        self.assertEqual(wizard.state, 'api_key')

    def test_api_key_empty_raises(self):
        wizard = self._new_wizard()
        wizard.state = 'api_key'
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_api_key_invalid_raises(self):
        wizard = self._new_wizard()
        wizard.state = 'api_key'
        wizard.api_key = 'bad-key'
        with patch.object(
            requests, 'get', return_value=self._mock_response(status_code=401),
        ):
            with self.assertRaises(UserError):
                wizard.action_next()

    def test_api_key_ok_advances_and_persists(self):
        wizard = self._new_wizard()
        wizard.state = 'api_key'
        wizard.api_key = 'll_key_valid'
        with patch.object(
            requests, 'get',
            return_value=self._mock_response({'authenticated': True}),
        ):
            wizard.action_next()
        self.assertEqual(wizard.state, 'acting_user')
        self.provider_record.invalidate_recordset()
        self.assertEqual(self.provider_record.api_key, 'll_key_valid')

    def test_acting_user_self_uses_current_user(self):
        wizard = self._new_wizard()
        wizard.state = 'acting_user'
        wizard.acting_user_mode = 'self'
        wizard.action_next()
        self.assertEqual(wizard.state, 'register')
        self.assertEqual(wizard.acting_user_id, self.env.user)

    def test_acting_user_existing_requires_selection(self):
        wizard = self._new_wizard()
        wizard.state = 'acting_user'
        wizard.acting_user_mode = 'existing'
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_register_requires_password(self):
        wizard = self._new_wizard()
        wizard.state = 'register'
        wizard.acting_user_id = self.env.user.id
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_register_completes_flow(self):
        wizard = self._new_wizard()
        wizard.state = 'register'
        wizard.acting_user_id = self.env.user.id
        wizard.acting_user_password = 'secret'
        with patch.object(
            requests, 'post',
            return_value=self._mock_response({'uid': 2}),
        ):
            wizard.action_next()
        self.assertEqual(wizard.state, 'done')
        self.assertFalse(wizard.acting_user_password)
        self.provider_record.invalidate_recordset()
        self.assertTrue(self.provider_record.agentidoo_session_registered)
        self.assertEqual(
            self.env.company.default_ai_provider_id, self.provider_record,
        )
        self.assertEqual(
            self.provider_record.agentidoo_acting_user_id, self.env.user,
        )

    def test_register_402_raises(self):
        wizard = self._new_wizard()
        wizard.state = 'register'
        wizard.acting_user_id = self.env.user.id
        wizard.acting_user_password = 'secret'
        with patch.object(
            requests, 'post',
            return_value=self._mock_response(
                {'error': 'Insufficient credits'}, status_code=402,
            ),
        ):
            with self.assertRaises(UserError):
                wizard.action_next()
