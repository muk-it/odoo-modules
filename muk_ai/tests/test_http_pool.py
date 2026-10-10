import http.client

import urllib3

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

    def test_the_pooled_session_replays_only_a_dropped_connection(self):
        retry = (
            ProviderBase._http_session()
            .get_adapter('https://api.openai.com')
            .max_retries
        )
        for reason in (
            ConnectionResetError(10054, 'reset by peer'),
            http.client.RemoteDisconnected('closed without response'),
            BrokenPipeError(32, 'broken pipe'),
        ):
            dropped = urllib3.exceptions.ProtocolError('Connection aborted.', reason)
            with self.subTest(reason=type(reason).__name__):
                self.assertEqual(
                    retry.increment('POST', '/v1/responses', error=dropped).connect,
                    retry.connect - 1,
                )
        for error in (
            urllib3.exceptions.ReadTimeoutError(None, '/v1/responses', 'timed out'),
            urllib3.exceptions.ProtocolError('Response ended prematurely'),
        ):
            with (
                self.subTest(error=type(error).__name__),
                self.assertRaises(type(error)),
            ):
                retry.increment('POST', '/v1/responses', error=error)
