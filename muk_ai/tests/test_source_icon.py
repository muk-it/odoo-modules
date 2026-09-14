from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests

import odoo.tests
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tests.common import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.base.models.ir_autovacuum import is_autovacuum
from odoo.addons.muk_ai.mcp import web as web_module
from odoo.addons.muk_ai.tests.common import HTML_PAGE, AITestCommon, PNG_1x1
from odoo.addons.muk_ai.tools import (
    FAVICON_BUDGET,
    FAVICON_DEADLINE,
    FAVICON_MAX_AGE_DAYS,
    FAVICON_MAX_BYTES,
    FAVICON_ROUTE,
)
from odoo.addons.muk_ai.tools.url_fetch import FetchResult

PNG_BYTES = base64.b64decode(PNG_1x1)
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

VENDOR_ICON = 'https://imgs.search.brave.com/abc/favicon.ico'


def icon_result(
    body: bytes = PNG_BYTES,
    url: str = 'https://example.com/favicon.ico',
    content_type: str = 'image/png',
) -> FetchResult:
    """Build a fetch result answering an icon request with ``body``."""
    return FetchResult(url=url, body=body, content_type=content_type, charset=None)


def brave_payload(url: str, favicon: str | None = None) -> dict:
    """Build a Brave search response carrying one hit, optionally with a favicon."""
    hit = {'url': url, 'title': 'A', 'description': 'desc'}
    if favicon:
        hit['meta_url'] = {'favicon': favicon}
    return {'web': {'results': [hit]}}


class Clock:
    """Monotonic stand-in advancing a fixed number of seconds per reading."""

    def __init__(self, step: float) -> None:
        self.step = step
        self.now = -step

    def __call__(self) -> float:
        """Return the next reading of this clock."""
        self.now += self.step
        return self.now


@tagged('post_install', '-at_install', 'muk_ai')
class SourceIconCase(AITestCommon):
    """Shared helpers for the per-domain source favicon cache."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @property
    def web(self) -> models.BaseModel:
        """Return the mixin carrying the web tools and their favicon cache."""
        return self.env['muk_mcp.mixin']

    def _cached(self, domain: str) -> models.BaseModel:
        """Return the cache attachment of ``domain``, asserting there is one."""
        rows = (
            self.env['ir.attachment']
            .sudo()
            .search([('url', '=', f'{FAVICON_ROUTE}/{domain}')])
        )
        self.assertEqual(len(rows), 1, f'expected one cached favicon for {domain}')
        return rows

    @contextmanager
    def _fetching(self, *results) -> Iterator[MagicMock]:
        """Patch the fetcher to answer with ``results``, one per call.

        :param results: a ``FetchResult`` or an exception instance per call
        """
        remaining = list(results)

        def fake(url, **kwargs):
            if not remaining:
                raise AssertionError(f'unexpected fetch of {url}')
            answer = remaining.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', side_effect=fake) as mock:
            yield mock

    def _search(self, url: str, favicon: str | None = None) -> dict:
        """Run the web_search tool against a stubbed Brave backend answering ``url``."""
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('muk_ai.search_backend', 'brave')
        params.set_param('muk_ai.search_api_key', 'k')
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = brave_payload(url, favicon)
        response.raise_for_status.return_value = None
        with patch.object(
            requests.Session, 'request', autospec=True, return_value=response
        ):
            return self.web._mcp_web_search(query='odoo')


class TestSourceIconDescriptors(SourceIconCase):
    """Verify no tool result or source descriptor carries a third-party icon URL."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_search_descriptor_carries_only_a_local_icon(self):
        with self._fetching(icon_result()) as mock:
            result = self._search('https://www.example.com/page', favicon=VENDOR_ICON)
        self.assertEqual(mock.call_args.args[0], VENDOR_ICON)
        self.assertEqual(result['results'][0]['icon'], f'{FAVICON_ROUTE}/example.com')
        self.assertNotIn(VENDOR_ICON, json.dumps(result))

    def test_fetch_descriptor_carries_only_a_local_icon(self):
        page = FetchResult(
            url='https://example.com/page',
            body=b'<html><head><link rel="icon" href="https://cdn.test/f.png"/>'
            b'</head><body>hi</body></html>',
            content_type='text/html',
            charset=None,
        )
        with self._fetching(page, icon_result()) as mock:
            result = self.web._mcp_web_fetch(url=page.url)
        self.assertEqual(mock.call_args.args[0], 'https://cdn.test/f.png')
        self.assertEqual(result['icon'], f'{FAVICON_ROUTE}/example.com')
        self.assertNotIn('cdn.test', json.dumps(result))

    def test_a_hit_without_a_declared_icon_guesses_favicon_ico(self):
        with self._fetching(icon_result()) as mock:
            result = self._search('https://plain.test/page')
        self.assertEqual(mock.call_args.args[0], 'https://plain.test/favicon.ico')
        self.assertEqual(result['results'][0]['icon'], f'{FAVICON_ROUTE}/plain.test')

    def test_one_call_fetches_each_cited_domain_once(self):
        targets = [
            ('https://example.com/a', None),
            ('https://www.example.com/b', 'https://cdn.test/f.png'),
            ('https://other.test/c', None),
        ]
        with self._fetching(icon_result(), icon_result()) as mock:
            routes = self.web._ai_cache_favicons(targets)
        self.assertEqual(mock.call_count, 2)
        self.assertEqual(
            routes,
            {
                'example.com': f'{FAVICON_ROUTE}/example.com',
                'other.test': f'{FAVICON_ROUTE}/other.test',
            },
        )
        self._cached('example.com')

    def test_an_already_cached_domain_is_not_fetched_again(self):
        with self._fetching(icon_result()):
            self._search('https://example.com/one', favicon=VENDOR_ICON)
        with self._fetching() as mock:
            result = self._search('https://www.example.com/two')
        mock.assert_not_called()
        self.assertEqual(result['results'][0]['icon'], f'{FAVICON_ROUTE}/example.com')
        self._cached('example.com')

    def test_targets_without_a_host_are_ignored(self):
        with self._fetching() as mock:
            self.assertEqual(
                self.web._ai_cache_favicons([('', None), ('not a url', None)]), {}
            )
        mock.assert_not_called()


class TestSourceIconRefusals(SourceIconCase):
    """Verify anything but a real raster icon is refused and never retried."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _refused(self, domain: str, answer) -> None:
        """Cache ``domain`` against a fetcher answering ``answer`` and assert a miss."""
        with self._fetching(answer):
            self.web._ai_cache_favicons([(f'https://{domain}/a', None)])
        self.assertIsNone(self.web._ai_favicon(domain))
        self.assertFalse(self._cached(domain).raw)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_real_icon_is_cached_under_the_byte_cap_and_the_deadline(self):
        with self._fetching(icon_result()) as mock:
            self.web._ai_cache_favicons([('https://example.com/a', None)])
        self.assertEqual(mock.call_args.kwargs['max_bytes'], FAVICON_MAX_BYTES)
        self.assertEqual(mock.call_args.kwargs['deadline'], FAVICON_DEADLINE)
        self.assertEqual(self.web._ai_favicon('example.com'), (PNG_BYTES, 'image/png'))

    def test_markup_answered_to_an_image_request_is_refused(self):
        self._refused(
            'liar.test', icon_result(body=HTML_PAGE, content_type='image/png')
        )

    def test_an_svg_icon_is_refused(self):
        self._refused(
            'vector.test', icon_result(body=SVG_BYTES, content_type='image/svg+xml')
        )

    def test_an_empty_body_is_refused(self):
        self._refused('empty.test', icon_result(body=b''))

    def test_an_oversized_response_is_refused(self):
        self._refused('huge.test', UserError('@url: response from x exceeds the cap.'))

    @mute_logger('odoo.tools.translate')
    def test_an_icon_pointing_at_an_internal_address_is_refused(self):
        with patch(
            'odoo.addons.muk_ai.tools.url_fetch.socket.getaddrinfo',
            return_value=[(0, 0, 0, '', ('127.0.0.1', 0))],
        ):
            self.web._ai_cache_favicons(
                [('https://hostile.test/a', 'https://hostile.test/f.png')]
            )
        self.assertIsNone(self.web._ai_favicon('hostile.test'))

    def test_a_dead_host_neither_fails_nor_delays_the_search(self):
        started = time.monotonic()
        with self._fetching(OSError('connection refused')):
            result = self._search('https://dead.test/page')
        self.assertLess(time.monotonic() - started, FAVICON_BUDGET)
        self.assertEqual(result['results'][0]['url'], 'https://dead.test/page')
        self.assertEqual(result['results'][0]['icon'], f'{FAVICON_ROUTE}/dead.test')

    def test_a_dead_host_is_remembered_and_never_refetched(self):
        with self._fetching(OSError('connection refused')):
            self._search('https://dead.test/page')
        with self._fetching() as mock:
            self.assertIsNone(self.web._ai_favicon('dead.test'))
            self._search('https://dead.test/other')
        mock.assert_not_called()

    def test_the_budget_leaves_the_remaining_domains_to_the_glyph(self):
        targets = [(f'https://host{index}.test/a', None) for index in range(3)]
        with (
            patch('odoo.addons.muk_ai.mcp.web.monotonic', Clock(FAVICON_BUDGET / 2)),
            self._fetching(icon_result()) as mock,
        ):
            routes = self.web._ai_cache_favicons(targets)
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(len(routes), 3)
        self.assertIsNone(self.web._ai_favicon('host2.test'))


@tagged('post_install', '-at_install', 'muk_ai')
class TestSourceIconRoute(odoo.tests.HttpCase):
    """Verify the icon route only serves what a tool call already cached."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _cache(self, domain: str, answer) -> None:
        """Cache the favicon of ``domain`` against a fetcher answering ``answer``."""
        with patch('odoo.addons.muk_ai.mcp.web.fetch_url', side_effect=[answer]):
            self.env['muk_mcp.mixin']._ai_cache_favicons(
                [(f'https://{domain}/a', None)]
            )
        self.env.flush_all()

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_cached_icon_is_served_as_an_image(self):
        self._cache('example.com', icon_result())
        self.authenticate('admin', 'admin')
        response = self.url_open(f'{FAVICON_ROUTE}/example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'image/png')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.content, PNG_BYTES)

    def test_an_unknown_domain_is_not_found(self):
        self.authenticate('admin', 'admin')
        self.assertEqual(
            self.url_open(f'{FAVICON_ROUTE}/attacker.test').status_code, 404
        )

    def test_a_refused_icon_is_not_found(self):
        self._cache('dead.test', OSError('connection refused'))
        self.authenticate('admin', 'admin')
        self.assertEqual(self.url_open(f'{FAVICON_ROUTE}/dead.test').status_code, 404)

    def test_the_route_never_fetches(self):
        self._cache('example.com', icon_result())
        self.authenticate('admin', 'admin')
        with patch(
            'odoo.addons.muk_ai.mcp.web.fetch_url',
            side_effect=AssertionError('the route triggered an outbound fetch'),
        ) as mock:
            self.assertEqual(
                self.url_open(f'{FAVICON_ROUTE}/example.com').status_code, 200
            )
            self.assertEqual(
                self.url_open(f'{FAVICON_ROUTE}/attacker.test').status_code, 404
            )
        mock.assert_not_called()

    def test_a_portal_user_is_not_served(self):
        self._cache('example.com', icon_result())
        new_test_user(
            self.env,
            login='icon-portal',
            password='icon-portal',
            groups='base.group_portal',
        )
        self.env.flush_all()
        self.authenticate('icon-portal', 'icon-portal')
        self.assertEqual(self.url_open(f'{FAVICON_ROUTE}/example.com').status_code, 404)


class TestSourceIconVacuum(SourceIconCase):
    """Verify the favicon cache is aged out and refilled by the next citation."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def setUp(self) -> None:
        """Freshen the favicons the database already holds, so only ours age out."""
        super().setUp()
        self.env.cr.execute(
            'UPDATE ir_attachment SET write_date = now() WHERE url LIKE %s',
            (f'{FAVICON_ROUTE}/%',),
        )
        self.env['ir.attachment'].invalidate_model(['write_date'])

    def _age(self, attachments: models.BaseModel, days: int) -> None:
        """Backdate ``write_date`` by ``days``, which the ORM would restamp."""
        self.env.cr.execute(
            'UPDATE ir_attachment SET write_date = %s WHERE id IN %s',
            (fields.Datetime.now() - timedelta(days=days), tuple(attachments.ids)),
        )
        attachments.invalidate_recordset(['write_date'])

    def _cache_icon(self, domain: str) -> models.BaseModel:
        """Cache a real favicon for ``domain`` and return its attachment."""
        with self._fetching(icon_result()):
            self.web._ai_cache_favicons([(f'https://{domain}/a', None)])
        return self._cached(domain)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_daily_vacuum_collects_the_sweep(self):
        self.assertTrue(is_autovacuum(type(self.web)._gc_favicons))

    def test_an_icon_nothing_cited_lately_is_deleted(self):
        attachment = self._cache_icon('gc-aged.test')
        self._age(attachment, FAVICON_MAX_AGE_DAYS + 1)
        self.assertEqual(self.web._gc_favicons(), (1, 0))
        self.assertFalse(attachment.exists())

    def test_a_recently_cited_icon_is_kept(self):
        attachment = self._cache_icon('gc-fresh.test')
        self._age(attachment, FAVICON_MAX_AGE_DAYS - 1)
        self.assertEqual(self.web._gc_favicons(), (0, 0))
        self.assertTrue(attachment.exists())

    def test_nothing_outside_the_icon_route_is_touched(self):
        bystanders = (
            self.env['ir.attachment']
            .sudo()
            .create(
                [
                    {'name': 'Near miss', 'url': '/muk_ai/source/icons/gc-near.test'},
                    {
                        'name': 'Filed under a record',
                        'url': f'{FAVICON_ROUTE}/gc-filed.test',
                        'res_model': 'res.partner',
                        'res_id': self.env.user.partner_id.id,
                    },
                    {'name': 'Plain file', 'raw': PNG_BYTES},
                ]
            )
        )
        self._age(bystanders, FAVICON_MAX_AGE_DAYS + 1)
        self.assertEqual(self.web._gc_favicons(), (0, 0))
        self.assertEqual(len(bystanders.exists()), 3)

    def test_a_domain_refused_once_is_tried_again_after_the_vacuum(self):
        with self._fetching(OSError('connection refused')):
            self.web._ai_cache_favicons([('https://gc-dead.test/a', None)])
        self._age(self._cached('gc-dead.test'), FAVICON_MAX_AGE_DAYS + 1)
        self.web._gc_favicons()
        with self._fetching(icon_result()) as mock:
            routes = self.web._ai_cache_favicons([('https://gc-dead.test/b', None)])
        mock.assert_called_once()
        self.assertEqual(routes['gc-dead.test'], f'{FAVICON_ROUTE}/gc-dead.test')
        self.assertEqual(self.web._ai_favicon('gc-dead.test'), (PNG_BYTES, 'image/png'))

    def test_a_vacuum_says_what_it_still_owes(self):
        for index in range(3):
            self._age(
                self._cache_icon(f'gc-batch{index}.test'), FAVICON_MAX_AGE_DAYS + 1
            )
        with patch.object(web_module, 'FAVICON_GC_BATCH', 2):
            self.assertEqual(self.web._gc_favicons(), (2, 1))
            self.assertEqual(self.web._gc_favicons(), (1, 0))
