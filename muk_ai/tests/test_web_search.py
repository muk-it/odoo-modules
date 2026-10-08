from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import patch

import requests

from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, json_response

BRAVE = 'https://api.search.brave.com/res/v1/web/search'
LINKUP = 'https://api.linkup.so/v1/search'
TAVILY = 'https://api.tavily.com/search'


class TestWebSearch(AITestCommon):
    """Verify the web_search tool against each backend, its settings and errors."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Locate the company in Austria and give the searching user German."""
        super().setUpClass()
        cls.env['res.lang']._activate_lang('de_DE')
        cls.env.company.country_id = cls.env.ref('base.at')
        cls.user = new_test_user(cls.env, login='ai-searcher', lang='de_DE')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _vendor(self, *responses) -> Iterator[list[dict]]:
        """Answer each search request with the next response, refusing icon lookups.

        A response is a payload sent as JSON, a ``requests.Response`` or an
        exception to raise. The yielded list collects every request sent.
        """
        remaining = list(responses)
        sent = []

        def request(self_arg, **kwargs) -> requests.Response:
            """Record the request and answer it with the next response."""
            sent.append(
                {key: value for key, value in kwargs.items() if key != 'timeout'}
            )
            answer = remaining.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return (
                answer
                if isinstance(answer, requests.Response)
                else json_response(answer)
            )

        with (
            patch.object(
                requests.Session, 'request', autospec=True, side_effect=request
            ),
            patch.object(socket, 'getaddrinfo', side_effect=socket.gaierror('offline')),
        ):
            yield sent

    def _search(self, **arguments) -> dict:
        """Run the web_search tool as the test user's chat does and decode it."""
        env = self.env(user=self.user)
        text, _info = env['muk_mcp.tool']._call('web_search', arguments, env)
        return json.loads(text)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_each_backend_maps_the_query_and_its_hits(self):
        for params, arguments, payload, request, hits in (
            (
                {'muk_ai.search_backend': 'brave', 'muk_ai.search_api_key': 'key'},
                {'query': 'odoo', 'count': 50, 'freshness': 'week', 'site': ' a.test '},
                {
                    'web': {
                        'results': [
                            {
                                'url': 'https://www.a.test/1',
                                'title': 'A',
                                'description': 'about a',
                                'page_age': '2026-01-02T00:00:00',
                            },
                            {'title': 'no url'},
                        ]
                    }
                },
                {
                    'method': 'GET',
                    'url': BRAVE,
                    'params': {
                        'q': 'odoo site:a.test',
                        'count': 10,
                        'safesearch': 'moderate',
                        'country': 'AT',
                        'search_lang': 'de',
                        'freshness': 'pw',
                    },
                    'headers': {
                        'Accept': 'application/json',
                        'X-Subscription-Token': 'key',
                    },
                },
                [
                    (
                        'https://www.a.test/1',
                        'A',
                        'about a',
                        'a.test',
                        '2026-01-02T00:00:00',
                    )
                ],
            ),
            (
                {
                    'muk_ai.search_backend': 'searxng',
                    'muk_ai.search_url': 'http://10.0.0.5/',
                },
                {'query': 'odoo', 'freshness': 'month', 'site': 'b.test'},
                {
                    'results': [
                        {
                            'url': 'https://b.test/2',
                            'title': 'B',
                            'content': 'about b',
                            'publishedDate': '2026-02-03',
                        }
                    ]
                },
                {
                    'method': 'GET',
                    'url': 'http://10.0.0.5/search',
                    'params': {
                        'q': 'odoo site:b.test',
                        'format': 'json',
                        'language': 'de-DE',
                        'time_range': 'month',
                    },
                },
                [('https://b.test/2', 'B', 'about b', 'b.test', '2026-02-03')],
            ),
            (
                {'muk_ai.search_backend': 'linkup', 'muk_ai.search_api_key': 'key'},
                {'query': 'odoo', 'freshness': 'week', 'site': 'c.test'},
                {
                    'results': [
                        {'type': 'text', 'name': 'C', 'url': 'https://c.test/3'},
                        {'type': 'image', 'name': 'I', 'url': 'https://c.test/i.png'},
                    ]
                },
                {
                    'method': 'POST',
                    'url': LINKUP,
                    'json': {
                        'q': 'odoo',
                        'depth': 'standard',
                        'outputType': 'searchResults',
                        'includeDomains': ['c.test'],
                        'fromDate': (date.today() - timedelta(days=7)).isoformat(),
                    },
                    'headers': {'Authorization': 'Bearer key'},
                },
                [('https://c.test/3', 'C', '', 'c.test', None)],
            ),
            (
                {'muk_ai.search_backend': 'tavily', 'muk_ai.search_api_key': 'key'},
                {'query': 'odoo', 'count': 2, 'freshness': 'year', 'site': 'd.test'},
                {
                    'results': [
                        {'url': f'https://d.test/{index}', 'title': f'D{index}'}
                        for index in range(5)
                    ]
                },
                {
                    'method': 'POST',
                    'url': TAVILY,
                    'json': {
                        'query': 'odoo',
                        'max_results': 2,
                        'include_favicon': True,
                        'include_domains': ['d.test'],
                        'time_range': 'year',
                    },
                    'headers': {'Authorization': 'Bearer key'},
                },
                [
                    ('https://d.test/0', 'D0', '', 'd.test', None),
                    ('https://d.test/1', 'D1', '', 'd.test', None),
                ],
            ),
        ):
            with self.subTest(backend=params['muk_ai.search_backend']):
                self._set_params(params)
                with self._vendor(payload) as sent:
                    result = self._search(**arguments)
                self.assertEqual(sent, [request])
                self.assertEqual(result['type'], 'web_search')
                self.assertEqual(result['backend'], params['muk_ai.search_backend'])
                self.assertEqual(
                    [
                        (
                            hit['url'],
                            hit['title'],
                            hit['snippet'],
                            hit['domain'],
                            hit['published'],
                        )
                        for hit in result['results']
                    ],
                    hits,
                )
                self.assertEqual(
                    {hit['icon'] for hit in result['results']},
                    {f'/muk_ai/source/icon/{hit[3]}' for hit in hits},
                )

    def test_the_search_speaks_the_company_country_and_the_user_language(self):
        self._set_params(
            {'muk_ai.search_backend': 'brave', 'muk_ai.search_api_key': 'key'}
        )
        for country, lang, locale in (
            ('base.at', 'de_DE', {'country': 'AT', 'search_lang': 'de'}),
            ('base.us', 'en_US', {'country': 'US', 'search_lang': 'en'}),
            (None, 'en_US', {'search_lang': 'en'}),
        ):
            with self.subTest(country=country, lang=lang):
                self.env.company.country_id = (
                    self.env.ref(country) if country else False
                )
                self.user.lang = lang
                with self._vendor({'web': {'results': []}}) as sent:
                    self._search(query='odoo')
                params = sent[0]['params']
                self.assertEqual(
                    {
                        key: params[key]
                        for key in ('country', 'search_lang')
                        if key in params
                    },
                    locale,
                )

    def test_a_failing_search_is_answered_not_raised(self):
        self.user.lang = 'en_US'
        invalid = requests.Response()
        invalid.status_code, invalid._content = 200, b'<html>'
        brave = {'muk_ai.search_backend': 'brave', 'muk_ai.search_api_key': 'key'}
        for params, answers, error in (
            ({'muk_ai.search_backend': ''}, (), 'No web search backend'),
            ({**brave, 'muk_ai.search_api_key': ''}, (), 'needs an API key'),
            (
                {'muk_ai.search_backend': 'searxng', 'muk_ai.search_url': ''},
                (),
                'needs a URL',
            ),
            (brave, (json_response({'message': 'rate limited'}, 429),), 'rate limited'),
            (brave, (requests.ConnectionError('connection refused'),), 'refused'),
            (brave, (invalid,), 'Web search (Brave Search) failed'),
        ):
            with self.subTest(error=error):
                self._set_params(params)
                with self._vendor(*answers) as sent:
                    result = self._search(query='odoo')
                self.assertEqual(set(result), {'query', 'error'})
                self.assertEqual(result['query'], 'odoo')
                self.assertIn(error, result['error'])
                self.assertEqual(len(sent), len(answers))

    def test_a_stored_url_reaches_only_the_backend_that_takes_one(self):
        settings = self.env['res.config.settings']
        settings.create(
            {
                'ai_search_backend': 'searxng',
                'ai_search_url': 'http://searxng.internal:8080',
            }
        ).execute()
        for code, endpoint in (
            ('searxng', 'http://searxng.internal:8080/search'),
            ('brave', BRAVE),
            ('linkup', LINKUP),
            ('tavily', TAVILY),
        ):
            with self.subTest(backend=code):
                settings.create(
                    {'ai_search_backend': code, 'ai_search_api_key': 'secret'}
                ).execute()
                with self._vendor({'web': {'results': []}, 'results': []}) as sent:
                    result = self._search(query='odoo')
                self.assertEqual(result['backend'], code)
                self.assertEqual(sent[0]['url'], endpoint)
                wire = json.dumps(sent, default=str)
                self.assertEqual('searxng.internal' in wire, code == 'searxng')
                self.assertEqual('secret' in wire, code != 'searxng')
