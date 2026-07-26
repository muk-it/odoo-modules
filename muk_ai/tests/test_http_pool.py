from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_ai.tests.common import AITestCommon


class TestAiHttpPool(AITestCommon):
    """Verify provider clients share one keep-alive HTTP session across rounds."""

    def test_http_session_is_shared_across_clients_and_providers(self):
        first = self.provider._get_client()._http_session()
        rebuilt = self.provider._get_client()._http_session()
        anthropic = self.provider_anthropic._get_client()._http_session()
        self.assertIs(rebuilt, first)
        self.assertIs(anthropic, first)
        self.assertIs(ProviderBase._http_session(), first)

    def test_https_adapter_pools_keep_alive_connections(self):
        adapter = ProviderBase._http_session().get_adapter('https://api.openai.com')
        self.assertEqual(adapter._pool_maxsize, 32)

    def test_adapter_retries_connect_only_never_replays_writes(self):
        retry = (
            ProviderBase._http_session()
            .get_adapter('https://api.openai.com')
            .max_retries
        )
        self.assertGreaterEqual(retry.connect, 1)
        self.assertIs(retry.read, False)
        self.assertEqual(retry.other, 0)
