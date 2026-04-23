from unittest.mock import MagicMock

from odoo.tests.common import TransactionCase

from odoo.addons.muk_ai_agentidoo.providers.agentidoo import AgentidooProvider


class AgentidooTestCommon(TransactionCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider_record = cls.env.ref('muk_ai_agentidoo.provider_agentidoo')
        cls.provider_record.sudo().write({'api_key': 'll_key_test'})
        cls.env.company.sudo().default_ai_provider_id = cls.provider_record
        cls.provider = cls.provider_record
        original_url = AgentidooProvider.default_url
        AgentidooProvider.default_url = 'https://agentidoo.test'
        cls.addClassCleanup(
            setattr, AgentidooProvider, 'default_url', original_url,
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _mock_response(self, body=None, status_code=200):
        response = MagicMock()
        response.ok = 200 <= status_code < 300
        response.status_code = status_code
        response.json.return_value = body or {}
        response.text = str(body or {})
        response.raise_for_status = MagicMock()
        return response
