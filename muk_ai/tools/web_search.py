from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple

import requests

from odoo import _
from odoo.api import Environment
from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools.http import http_session

# ----------------------------------------------------------
# Search Limits
# ----------------------------------------------------------

SEARCH_TIMEOUT = 20
WEB_SEARCH_MAX_RESULTS = 10
FRESHNESS_DAYS = {'day': 1, 'week': 7, 'month': 30, 'year': 365}


class SearchHit(NamedTuple):
    """One normalized web search result."""

    url: str
    title: str
    snippet: str
    published: str | None
    icon: str | None


class SearchQuery(NamedTuple):
    """A web search request before a backend maps it to its wire form.

    ``country`` is the ISO code of the company, ``language`` the Odoo locale
    of the user; each backend maps what it can express and ignores the rest.
    """

    query: str
    count: int = 8
    country: str = ''
    language: str = ''
    freshness: str | None = None
    site: str | None = None

    @property
    def language_code(self) -> str:
        """Return the bare language of the locale (``de`` for ``de_AT``)."""
        return self.language.split('_')[0] if self.language else ''

    @property
    def since(self) -> str | None:
        """Return the ISO date the freshness window starts at, or ``None``."""
        if days := FRESHNESS_DAYS.get(self.freshness or ''):
            return (date.today() - timedelta(days=days)).isoformat()
        return None

    @property
    def scoped_query(self) -> str:
        """Return the query with the ``site:`` operator applied, when a site is set."""
        return f'{self.query} site:{self.site}' if self.site else self.query


class SearchBackend:
    """Base class for web search adapters: auth, query mapping, result mapping.

    The URL and API key are admin-supplied, so the request deliberately bypasses
    the SSRF guard of :func:`fetch_url` — only the query text is model-controlled,
    and every result URL the model later reads still goes through that guard.
    """

    code = ''
    label = ''
    default_url = ''
    needs_key = True
    needs_url = False

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    def __init__(self, api_key: str = '', url: str = '') -> None:
        """Store the credentials, honouring ``url`` only where the backend takes one.

        A vendor backend answers at its own endpoint, so ``url`` is ignored
        unless the backend declares ``needs_url``: a leftover URL from another
        backend must never send the API key to an unrelated host.
        """
        self.api_key = api_key or ''
        self.url = (url if self.needs_url else self.default_url).rstrip('/')

    # ----------------------------------------------------------
    # Contract
    # ----------------------------------------------------------

    def build_request(self, query: SearchQuery) -> dict:
        """Return the ``requests.Session.request`` keyword arguments for ``query``."""
        raise NotImplementedError

    def parse(self, payload: dict) -> list[SearchHit]:
        """Map the decoded response body to normalized hits."""
        raise NotImplementedError

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def search(self, query: SearchQuery) -> list[SearchHit]:
        """Run ``query`` against the backend and return at most ``query.count`` hits.

        :raise UserError: when the backend is not fully configured, the request
            fails, or the response is not JSON
        """
        if self.needs_key and not self.api_key:
            raise UserError(_('Web search backend %s needs an API key.', self.label))
        if self.needs_url and not self.url:
            raise UserError(_('Web search backend %s needs a URL.', self.label))
        try:
            response = http_session().request(
                timeout=SEARCH_TIMEOUT,
                **self.build_request(query),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as error:
            detail = getattr(error.response, 'text', '') or str(error)
            raise UserError(
                _('Web search (%s) failed: %s', self.label, detail[:500])
            ) from error
        except (requests.RequestException, ValueError) as error:
            raise UserError(
                _('Web search (%s) failed: %s', self.label, error)
            ) from error
        return self.parse(payload)[: query.count]


# ----------------------------------------------------------
# Adapters
# ----------------------------------------------------------


class BraveBackend(SearchBackend):
    """Brave Search API: header-authenticated GET with region and freshness."""

    code = 'brave'
    label = 'Brave Search'
    default_url = 'https://api.search.brave.com/res/v1'
    freshness = {'day': 'pd', 'week': 'pw', 'month': 'pm', 'year': 'py'}

    def build_request(self, query: SearchQuery) -> dict:
        """Map the query to Brave's ``web/search`` parameters."""
        params = {
            'q': query.scoped_query,
            'count': query.count,
            'safesearch': 'moderate',
        }
        if query.country:
            params['country'] = query.country.upper()
        if query.language_code:
            params['search_lang'] = query.language_code
        if freshness := self.freshness.get(query.freshness or ''):
            params['freshness'] = freshness
        return {
            'method': 'GET',
            'url': f'{self.url}/web/search',
            'params': params,
            'headers': {
                'Accept': 'application/json',
                'X-Subscription-Token': self.api_key,
            },
        }

    def parse(self, payload: dict) -> list[SearchHit]:
        """Read ``web.results[]`` with its page age and favicon."""
        return [
            SearchHit(
                url=entry.get('url') or '',
                title=entry.get('title') or '',
                snippet=entry.get('description') or '',
                published=entry.get('page_age') or None,
                icon=(entry.get('meta_url') or {}).get('favicon') or None,
            )
            for entry in (payload.get('web') or {}).get('results') or []
            if entry.get('url')
        ]


class SearXNGBackend(SearchBackend):
    """Self-hosted SearXNG instance queried through its JSON format.

    The instance must list ``json`` under ``search.formats`` in its
    settings, otherwise it answers 403 to the format parameter.
    """

    code = 'searxng'
    label = 'SearXNG'
    needs_key = False
    needs_url = True

    def build_request(self, query: SearchQuery) -> dict:
        """Map the query to SearXNG's ``search`` parameters."""
        params = {'q': query.scoped_query, 'format': 'json'}
        if query.language:
            params['language'] = query.language.replace('_', '-')
        if query.freshness in FRESHNESS_DAYS:
            params['time_range'] = query.freshness
        return {'method': 'GET', 'url': f'{self.url}/search', 'params': params}

    def parse(self, payload: dict) -> list[SearchHit]:
        """Read ``results[]`` with its published date."""
        return [
            SearchHit(
                url=entry.get('url') or '',
                title=entry.get('title') or '',
                snippet=entry.get('content') or '',
                published=entry.get('publishedDate') or None,
                icon=None,
            )
            for entry in payload.get('results') or []
            if entry.get('url')
        ]


class LinkupBackend(SearchBackend):
    """Linkup search API: bearer-authenticated POST returning raw results."""

    code = 'linkup'
    label = 'Linkup'
    default_url = 'https://api.linkup.so/v1'

    def build_request(self, query: SearchQuery) -> dict:
        """Map the query to Linkup's ``search`` body."""
        body = {
            'q': query.query,
            'depth': 'standard',
            'outputType': 'searchResults',
        }
        if query.site:
            body['includeDomains'] = [query.site]
        if since := query.since:
            body['fromDate'] = since
        return {
            'method': 'POST',
            'url': f'{self.url}/search',
            'json': body,
            'headers': {'Authorization': f'Bearer {self.api_key}'},
        }

    def parse(self, payload: dict) -> list[SearchHit]:
        """Read ``results[]``, keeping the text entries."""
        return [
            SearchHit(
                url=entry.get('url') or '',
                title=entry.get('name') or '',
                snippet=entry.get('content') or '',
                published=None,
                icon=None,
            )
            for entry in payload.get('results') or []
            if entry.get('url') and entry.get('type', 'text') == 'text'
        ]


class TavilyBackend(SearchBackend):
    """Tavily search API: bearer-authenticated POST with scored results."""

    code = 'tavily'
    label = 'Tavily'
    default_url = 'https://api.tavily.com'

    def build_request(self, query: SearchQuery) -> dict:
        """Map the query to Tavily's ``search`` body."""
        body = {
            'query': query.query,
            'max_results': query.count,
            'include_favicon': True,
        }
        if query.site:
            body['include_domains'] = [query.site]
        if query.freshness in FRESHNESS_DAYS:
            body['time_range'] = query.freshness
        return {
            'method': 'POST',
            'url': f'{self.url}/search',
            'json': body,
            'headers': {'Authorization': f'Bearer {self.api_key}'},
        }

    def parse(self, payload: dict) -> list[SearchHit]:
        """Read ``results[]`` with its published date and favicon."""
        return [
            SearchHit(
                url=entry.get('url') or '',
                title=entry.get('title') or '',
                snippet=entry.get('content') or '',
                published=entry.get('published_date') or None,
                icon=entry.get('favicon') or None,
            )
            for entry in payload.get('results') or []
            if entry.get('url')
        ]


# ----------------------------------------------------------
# Registry
# ----------------------------------------------------------

SEARCH_BACKENDS: dict[str, type[SearchBackend]] = {
    cls.code: cls
    for cls in (
        BraveBackend,
        SearXNGBackend,
        LinkupBackend,
        TavilyBackend,
    )
}


def search_backend(env: Environment) -> SearchBackend | None:
    """Return the configured backend, or ``None`` when web search is unset."""
    params = env['ir.config_parameter'].sudo()
    if (cls := SEARCH_BACKENDS.get(params.get_param('muk_ai.search_backend'))) is None:
        return None
    return cls(
        api_key=params.get_param('muk_ai.search_api_key') or '',
        url=params.get_param('muk_ai.search_url') or '',
    )
