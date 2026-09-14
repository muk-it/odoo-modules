from __future__ import annotations

import json
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.openai import OpenAIProvider
from odoo.addons.muk_ai.tests.common import AITestCommon, ToolCatalogMixin
from odoo.addons.muk_ai.tools.sources import extract_sources
from odoo.addons.muk_ai.tools.web_search import (
    SEARCH_BACKENDS,
    BraveBackend,
    LinkupBackend,
    SearchBackend,
    SearchQuery,
    SearXNGBackend,
    TavilyBackend,
    search_backend,
)
from odoo.addons.muk_mcp.core.tool import get_tool_index


class WebSearchCase(AITestCommon):
    """Shared helpers configuring a search backend and mocking its HTTP call."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _configure(self, backend: str | None, key: str = 'k', url: str = '') -> None:
        """Store the web search settings as the settings form would."""
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('muk_ai.search_backend', backend or False)
        params.set_param('muk_ai.search_api_key', key or False)
        params.set_param('muk_ai.search_url', url or False)

    def _mock_search(
        self, payload: dict, captured: dict | None = None
    ) -> AbstractContextManager[MagicMock]:
        """Patch the pooled HTTP session to answer ``payload``, recording the call."""

        def fake(self_arg, **kwargs):
            if captured is not None:
                captured.update(kwargs)
            return self._mock_http_response(payload)

        return patch.object(
            requests.Session, 'request', autospec=True, side_effect=fake
        )

    def _hits(self, *urls: str) -> list[dict]:
        """Build web search results for the given urls."""
        return [
            {'url': url, 'title': f'T{index}', 'snippet': 's', 'domain': 'x'}
            for index, url in enumerate(urls)
        ]


class TestSearchBackends(WebSearchCase):
    """Verify each backend's query mapping, result mapping and error handling."""

    # ----------------------------------------------------------
    # Tests: adapters
    # ----------------------------------------------------------

    def test_registry_lists_the_four_core_backends(self):
        self.assertEqual(
            list(SEARCH_BACKENDS), ['brave', 'searxng', 'linkup', 'tavily']
        )

    def test_brave_maps_query_and_results(self):
        captured = {}
        payload = {
            'web': {
                'results': [
                    {
                        'url': 'https://a.test/1',
                        'title': 'A',
                        'description': 'desc',
                        'page_age': '2026-01-02T00:00:00',
                        'meta_url': {'favicon': 'https://a.test/favicon.ico'},
                    },
                    {'title': 'no url'},
                ]
            }
        }
        query = SearchQuery(
            'odoo', count=5, country='at', language='de_AT', freshness='week'
        )
        with self._mock_search(payload, captured):
            hits = BraveBackend(api_key='token').search(query)
        self.assertEqual(captured['method'], 'GET')
        self.assertEqual(
            captured['url'], 'https://api.search.brave.com/res/v1/web/search'
        )
        self.assertEqual(captured['headers']['X-Subscription-Token'], 'token')
        self.assertEqual(captured['params']['q'], 'odoo')
        self.assertEqual(captured['params']['count'], 5)
        self.assertEqual(captured['params']['country'], 'AT')
        self.assertEqual(captured['params']['search_lang'], 'de')
        self.assertEqual(captured['params']['freshness'], 'pw')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].url, 'https://a.test/1')
        self.assertEqual(hits[0].snippet, 'desc')
        self.assertEqual(hits[0].published, '2026-01-02T00:00:00')
        self.assertEqual(hits[0].icon, 'https://a.test/favicon.ico')

    def test_brave_site_restriction_uses_the_site_operator(self):
        captured = {}
        with self._mock_search({'web': {'results': []}}, captured):
            BraveBackend(api_key='token').search(
                SearchQuery('odoo', site='docs.odoo.com')
            )
        self.assertEqual(captured['params']['q'], 'odoo site:docs.odoo.com')
        self.assertNotIn('freshness', captured['params'])
        self.assertNotIn('country', captured['params'])

    def test_searxng_maps_query_and_results(self):
        captured = {}
        payload = {
            'results': [
                {
                    'url': 'https://b.test/2',
                    'title': 'B',
                    'content': 'body',
                    'publishedDate': '2026-02-03',
                }
            ]
        }
        query = SearchQuery('odoo', language='de_AT', freshness='month', site='b.test')
        with self._mock_search(payload, captured):
            hits = SearXNGBackend(url='http://searxng:8080/').search(query)
        self.assertEqual(captured['url'], 'http://searxng:8080/search')
        self.assertEqual(captured['params']['format'], 'json')
        self.assertEqual(captured['params']['q'], 'odoo site:b.test')
        self.assertEqual(captured['params']['language'], 'de-AT')
        self.assertEqual(captured['params']['time_range'], 'month')
        self.assertNotIn('headers', captured)
        self.assertEqual(hits[0].title, 'B')
        self.assertEqual(hits[0].snippet, 'body')
        self.assertEqual(hits[0].published, '2026-02-03')
        self.assertIsNone(hits[0].icon)

    def test_linkup_maps_query_and_results(self):
        captured = {}
        payload = {
            'results': [
                {
                    'type': 'text',
                    'name': 'C',
                    'url': 'https://c.test/3',
                    'content': 'c',
                },
                {'type': 'image', 'name': 'img', 'url': 'https://c.test/i.png'},
            ]
        }
        query = SearchQuery('odoo', freshness='day', site='c.test')
        with self._mock_search(payload, captured):
            hits = LinkupBackend(api_key='token').search(query)
        self.assertEqual(captured['method'], 'POST')
        self.assertEqual(captured['url'], 'https://api.linkup.so/v1/search')
        self.assertEqual(captured['headers']['Authorization'], 'Bearer token')
        self.assertEqual(captured['json']['q'], 'odoo')
        self.assertEqual(captured['json']['outputType'], 'searchResults')
        self.assertEqual(captured['json']['includeDomains'], ['c.test'])
        self.assertEqual(captured['json']['fromDate'], query.since)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].title, 'C')

    def test_tavily_maps_query_and_results(self):
        captured = {}
        payload = {
            'results': [
                {
                    'url': 'https://d.test/4',
                    'title': 'D',
                    'content': 'd',
                    'score': 0.9,
                    'published_date': '2026-03-04',
                    'favicon': 'https://d.test/f.ico',
                }
            ]
        }
        query = SearchQuery('odoo', count=3, freshness='year', site='d.test')
        with self._mock_search(payload, captured):
            hits = TavilyBackend(api_key='token').search(query)
        self.assertEqual(captured['url'], 'https://api.tavily.com/search')
        self.assertEqual(captured['headers']['Authorization'], 'Bearer token')
        self.assertEqual(captured['json']['query'], 'odoo')
        self.assertEqual(captured['json']['max_results'], 3)
        self.assertEqual(captured['json']['include_domains'], ['d.test'])
        self.assertEqual(captured['json']['time_range'], 'year')
        self.assertEqual(hits[0].published, '2026-03-04')
        self.assertEqual(hits[0].icon, 'https://d.test/f.ico')

    def test_results_are_capped_at_the_requested_count(self):
        payload = {'results': [{'url': f'https://e.test/{i}'} for i in range(20)]}
        with self._mock_search(payload):
            hits = SearXNGBackend(url='http://s').search(SearchQuery('q', count=4))
        self.assertEqual(len(hits), 4)

    # ----------------------------------------------------------
    # Tests: configuration and errors
    # ----------------------------------------------------------

    def test_missing_key_or_url_raises_before_any_request(self):
        with self.assertRaises(UserError):
            BraveBackend().search(SearchQuery('q'))
        with self.assertRaises(UserError):
            SearXNGBackend().search(SearchQuery('q'))

    def test_http_failure_becomes_a_user_error(self):
        response = MagicMock(status_code=429, text='rate limited')
        error = requests.HTTPError(response=response)
        with (
            patch.object(requests.Session, 'request', side_effect=error),
            self.assertRaises(UserError) as caught,
        ):
            BraveBackend(api_key='k').search(SearchQuery('q'))
        self.assertIn('rate limited', str(caught.exception))

    def test_admin_url_bypasses_the_model_facing_fetch_guard(self):
        captured = {}
        guard = patch(
            'odoo.addons.muk_ai.tools.url_fetch._validate_url',
            side_effect=AssertionError('search must not go through fetch_url'),
        )
        with guard, self._mock_search({'results': []}, captured):
            SearXNGBackend(url='http://10.0.0.5:8080').search(SearchQuery('q'))
        self.assertEqual(captured['url'], 'http://10.0.0.5:8080/search')

    def test_search_backend_follows_the_settings(self):
        self._configure(None)
        self.assertIsNone(search_backend(self.env))
        self._configure('tavily', key='secret')
        backend = search_backend(self.env)
        self.assertIsInstance(backend, TavilyBackend)
        self.assertEqual(backend.api_key, 'secret')
        self._configure('searxng', key='', url='http://searxng:8080')
        backend = search_backend(self.env)
        self.assertIsInstance(backend, SearXNGBackend)
        self.assertEqual(backend.url, 'http://searxng:8080')

    def test_settings_form_offers_the_registered_backends(self):
        settings = self.env['res.config.settings'].create({})
        codes = [
            code
            for code, _ in settings._fields['ai_search_backend'].selection(settings)
        ]
        self.assertEqual(codes, list(SEARCH_BACKENDS))


class TestSearchUrlBinding(WebSearchCase):
    """Verify a stored custom URL only reaches the backend that declares one."""

    searxng_url = 'http://searxng.internal:8080'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _capture_request(self, backend: SearchBackend) -> dict:
        """Run a search through ``backend`` and return the request it issued."""
        captured = {}
        with self._mock_search({'web': {'results': []}, 'results': []}, captured):
            backend.search(SearchQuery('odoo'))
        return captured

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_keyed_backends_never_receive_a_custom_url(self):
        cases = (
            (
                'brave',
                'https://api.search.brave.com/res/v1/web/search',
                'X-Subscription-Token',
                'key',
            ),
            (
                'linkup',
                'https://api.linkup.so/v1/search',
                'Authorization',
                'Bearer key',
            ),
            (
                'tavily',
                'https://api.tavily.com/search',
                'Authorization',
                'Bearer key',
            ),
        )
        for code, endpoint, header, value in cases:
            with self.subTest(backend=code):
                self._configure(code, key='key', url=self.searxng_url)
                backend = search_backend(self.env)
                self.assertEqual(backend.url, SEARCH_BACKENDS[code].default_url)
                captured = self._capture_request(backend)
                self.assertEqual(captured['url'], endpoint)
                self.assertEqual(captured['headers'][header], value)
                self.assertNotIn('searxng.internal', json.dumps(captured, default=str))

    def test_searxng_is_still_served_from_its_url(self):
        self._configure('searxng', key='', url=self.searxng_url)
        backend = search_backend(self.env)
        self.assertEqual(backend.url, self.searxng_url)
        captured = self._capture_request(backend)
        self.assertEqual(captured['url'], f'{self.searxng_url}/search')
        self.assertNotIn('headers', captured)

    def test_switching_off_searxng_keeps_the_key_on_the_new_endpoint(self):
        self._configure('searxng', key='', url=self.searxng_url)
        self.assertEqual(
            self._capture_request(search_backend(self.env))['url'],
            f'{self.searxng_url}/search',
        )
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('muk_ai.search_backend', 'brave')
        params.set_param('muk_ai.search_api_key', 'key')
        self.assertEqual(params.get_param('muk_ai.search_url'), self.searxng_url)
        captured = {}
        with self._mock_search({'web': {'results': []}}, captured):
            result = self.env['muk_mcp.mixin']._mcp_web_search(query='odoo')
        self.assertEqual(result['backend'], 'brave')
        self.assertEqual(
            captured['url'], 'https://api.search.brave.com/res/v1/web/search'
        )
        self.assertEqual(captured['headers']['X-Subscription-Token'], 'key')
        self.assertNotIn('searxng.internal', json.dumps(captured, default=str))


class TestWebSearchTool(WebSearchCase):
    """Verify the web_search MCP tool result shape, localization and errors."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_tool_registered_in_odoo_catalog(self):
        index = get_tool_index(self.env, registry='odoo')
        self.assertIn('web_search', index)
        self.assertEqual(index['web_search']['category'], 'read')
        self.assertIn('personal data', index['web_search']['description'])

    def test_without_backend_the_tool_reports_an_error(self):
        self._configure(None)
        result = self.env['muk_mcp.mixin']._mcp_web_search(query='odoo')
        self.assertEqual(result['query'], 'odoo')
        self.assertIn('No web search backend', result['error'])

    def test_result_descriptor_and_localization(self):
        self._configure('brave', key='k')
        self.env.company.country_id = self.env.ref('base.at')
        self.env.user.lang = 'en_US'
        captured = {}
        payload = {
            'web': {
                'results': [
                    {
                        'url': 'https://www.example.com/page',
                        'title': 'Example',
                        'description': 'snippet',
                    }
                ]
            }
        }
        icons = patch(
            'odoo.addons.muk_ai.mcp.web.fetch_url',
            side_effect=OSError('no icon host in tests'),
        )
        with icons, self._mock_search(payload, captured):
            result = self.env['muk_mcp.mixin']._mcp_web_search(
                query='odoo', count=50, freshness='bogus', site=' example.com '
            )
        self.assertEqual(captured['params']['country'], 'AT')
        self.assertEqual(captured['params']['search_lang'], 'en')
        self.assertEqual(captured['params']['count'], 10)
        self.assertEqual(captured['params']['q'], 'odoo site:example.com')
        self.assertNotIn('freshness', captured['params'])
        self.assertEqual(result['type'], 'web_search')
        self.assertEqual(result['backend'], 'brave')
        self.assertEqual(result['query'], 'odoo')
        hit = result['results'][0]
        self.assertEqual(hit['url'], 'https://www.example.com/page')
        self.assertEqual(hit['title'], 'Example')
        self.assertEqual(hit['snippet'], 'snippet')
        self.assertEqual(hit['domain'], 'example.com')
        self.assertIsNone(hit['published'])
        self.assertEqual(hit['icon'], '/muk_ai/source/icon/example.com')

    def test_backend_error_returned_not_raised(self):
        self._configure('brave', key='')
        result = self.env['muk_mcp.mixin']._mcp_web_search(query='odoo')
        self.assertEqual(result['query'], 'odoo')
        self.assertIn('API key', result['error'])
        self.assertNotIn('results', result)


class TestWebSearchSources(WebSearchCase):
    """Verify web_search hits become web sources merging with web_fetch."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_hits_share_the_web_fetch_source_id(self):
        url = 'https://www.example.com/page'
        search = {
            'type': 'web_search',
            'results': [
                {'url': url, 'title': 'Hit', 'icon': '/muk_ai/source/icon/example.com'}
            ],
        }
        fetch = {'type': 'web', 'url': url, 'title': 'Fetched'}
        from_search = extract_sources('web_search', {'query': 'q'}, search)[0]
        from_fetch = extract_sources('web_fetch', {'url': url}, fetch)[0]
        self.assertEqual(from_search['id'], from_fetch['id'])
        self.assertEqual(from_search['id'], f'web:{url}')
        self.assertEqual(from_search['type'], 'web')
        self.assertEqual(from_search['domain'], 'example.com')
        self.assertEqual(from_search['icon'], '/muk_ai/source/icon/example.com')

    def test_sources_are_capped_at_ten(self):
        result = {'results': self._hits(*[f'https://x.test/{i}' for i in range(15)])}
        self.assertEqual(len(extract_sources('web_search', {}, result)), 10)

    def test_error_or_urlless_hits_yield_no_source(self):
        self.assertEqual(
            extract_sources('web_search', {}, {'query': 'q', 'error': 'x'}), []
        )
        self.assertEqual(
            extract_sources('web_search', {}, {'results': [{'title': 'no url'}]}),
            [],
        )

    def test_serialized_result_is_parsed(self):
        text = json.dumps({'results': self._hits('https://y.test/1')}, indent=2)
        self.assertEqual(
            extract_sources('web_search', {}, text)[0]['id'], 'web:https://y.test/1'
        )


class TestWebSearchRoute(ToolCatalogMixin, WebSearchCase):
    """Verify the session picks exactly one search capability per round."""

    catalog = [
        {'name': 'web_search', 'description': 'search', 'inputSchema': {}},
        {'name': 'web_fetch', 'description': 'fetch', 'inputSchema': {}},
    ]

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self._configure(None)
        self.agent = self.env['muk_ai.agent'].create(
            {'name': 'Searcher', 'web_search': 'auto'}
        )
        self.session = self.env['muk_ai.session'].create(
            {'name': 'route', 'agent_id': self.agent.id}
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _catalog_names(self) -> set[str]:
        """Return the tool names the session currently offers."""
        with self._patch_catalog():
            return {entry['name'] for entry in self.session._get_filtered_catalog()}

    # ----------------------------------------------------------
    # Tests: route resolution
    # ----------------------------------------------------------

    def test_native_serves_when_no_backend_is_configured(self):
        self.assertEqual(self.agent._web_search_route(), 'native')

    def test_configured_backend_beats_the_native_connector(self):
        self._configure('brave')
        self.assertEqual(self.agent._web_search_route(), 'tool')

    def test_backend_serves_providers_without_native_search(self):
        with patch.object(OpenAIProvider, 'supports_web_search', False):
            self.env.invalidate_all()
            self.assertIsNone(self.agent._web_search_route())
            self._configure('brave')
            self.assertEqual(self.agent._web_search_route(), 'tool')

    def test_disabled_agent_has_no_route(self):
        self.agent.web_search = 'off'
        self._configure('brave')
        self.assertIsNone(self.agent._web_search_route())
        self.assertIsNone(self.env['muk_ai.agent']._web_search_route())

    def test_an_explicit_backend_route_never_falls_back_to_the_connector(self):
        self.agent.web_search = 'tool'
        self.assertIsNone(self.agent._web_search_route())
        self.assertIn(
            'no Web Search Backend is configured',
            self.agent.capability_warning,
        )
        self._configure('brave')
        self.env.invalidate_all()
        self.assertEqual(self.agent._web_search_route(), 'tool')
        self.assertFalse(self.agent.capability_warning)

    def test_an_explicit_native_route_never_falls_back_to_the_backend(self):
        self.agent.web_search = 'native'
        self._configure('brave')
        self.env.invalidate_all()
        self.assertEqual(self.agent._web_search_route(), 'native')
        with patch.object(OpenAIProvider, 'supports_web_search', False):
            self.env.invalidate_all()
            self.assertIsNone(self.agent._web_search_route())
            self.assertIn(
                'serves no built-in search',
                self.agent.capability_warning,
            )

    # ----------------------------------------------------------
    # Tests: catalogue and provider flags
    # ----------------------------------------------------------

    def test_catalogue_offers_the_tool_only_on_the_tool_route(self):
        self.assertEqual(self._catalog_names(), {'web_fetch'})
        self._configure('brave')
        self.assertEqual(self._catalog_names(), {'web_fetch', 'web_search'})
        self.agent.web_search = 'off'
        self.assertEqual(self._catalog_names(), {'web_fetch'})

    def test_a_filter_hiding_the_tool_kills_the_backend_route(self):
        self._configure('brave')
        self.agent.write({'web_search': 'tool', 'tool_filter': ['web_fetch']})
        self.env.invalidate_all()
        self.assertIsNone(self.agent._web_search_route())
        self.assertEqual(self._catalog_names(), {'web_fetch'})
        self.assertIn(
            'does not list "web_search"',
            self.agent.capability_warning,
        )

    def test_automatic_falls_back_to_the_connector_when_the_filter_hides_the_tool(self):
        self._configure('brave')
        self.agent.tool_filter = ['web_fetch']
        self.env.invalidate_all()
        self.assertEqual(self.agent._web_search_route(), 'native')
        self.assertFalse(self.agent.capability_warning)

    def test_provider_flag_follows_the_route(self):
        with self._mock_responses([self._make_text_response()]) as mock:
            self.session.start('go')
        self.assertTrue(mock.call_args.kwargs['enable_web_search'])
        self._configure('brave')
        with self._mock_responses([self._make_text_response()]) as mock:
            self.session.send_message('again')
        self.assertFalse(mock.call_args.kwargs['enable_web_search'])
