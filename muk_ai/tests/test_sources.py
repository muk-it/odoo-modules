from __future__ import annotations

import ipaddress
import itertools
import json
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import models
from odoo.tests import HttpCase, new_test_user

from odoo.addons.muk_ai.tests.common import (
    HTML_PAGE,
    PNG_BYTES,
    AITestCommon,
    PNG_1x1,
    json_response,
    serve_web,
    text_payload,
    tool_payload,
)
from odoo.addons.muk_ai.tools.sources import extract_sources, web_icon_url
from odoo.addons.muk_ai.tools.url_fetch import (
    FAVICON_BUDGET,
    FAVICON_GC_BATCH,
    FAVICON_MAX_AGE_DAYS,
    FAVICON_MAX_BYTES,
)

ROUTE = '/muk_ai/source/icon'

SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

ICO_BYTES = (
    bytes.fromhex('0000010001001010000001002000')
    + len(PNG_BYTES).to_bytes(4, 'little')
    + (22).to_bytes(4, 'little')
    + PNG_BYTES
)


class WebMixin:
    """Serve pages and icons at the network boundary of the web tools."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _tool(self, name: str, arguments: dict) -> dict:
        """Run a tool as a chat dispatches it and decode its result."""
        text, _info = self.env['muk_mcp.tool']._call(name, arguments, self.env)
        return json.loads(text)


class TestSources(WebMixin, AITestCommon):
    """Verify the sources a tool call cites and the favicon cache behind them."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Open partners and agents from a test app, tags from an icon-less one."""
        super().setUpClass()
        menus = cls.env['ir.ui.menu']
        app = menus.create(
            {
                'name': 'Test App',
                'sequence': -1000,
                'web_icon': 'muk_mcp,static/description/icon.png',
            }
        )
        unset = menus.create(
            {
                'name': 'Test Unset App',
                'sequence': -1000,
                'web_icon': 'base,static/description/icon.png',
            }
        )
        for root, model in (
            (app, 'res.partner'),
            (app, 'muk_ai.agent'),
            (unset, 'res.partner.category'),
        ):
            action = cls.env['ir.actions.act_window'].create(
                {'name': model, 'res_model': model}
            )
            menus.create(
                {
                    'name': model,
                    'parent_id': root.id,
                    'action': f'ir.actions.act_window,{action.id}',
                }
            )

    def setUp(self) -> None:
        """Freshen the favicons the database already holds, so only ours age."""
        super().setUp()
        if cached := self.env['ir.attachment'].search([('url', '=like', f'{ROUTE}/%')]):
            self._backdate(cached, timedelta(0))

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _search(self, *targets: tuple[str, str | None]) -> dict:
        """Run web_search against a Brave backend answering one hit per target.

        :param targets: ``(page url, favicon url or None)`` of each hit
        """
        self._set_params(
            {'muk_ai.search_backend': 'brave', 'muk_ai.search_api_key': 'key'}
        )
        hits = [
            {'url': url, 'title': url, 'meta_url': {'favicon': icon}}
            for url, icon in targets
        ]
        with patch.object(
            requests.Session,
            'request',
            autospec=True,
            return_value=json_response({'web': {'results': hits}}),
        ):
            return self._tool('web_search', {'query': 'odoo'})

    def _icon(self, domain: str) -> models.BaseModel:
        """Return the cached favicon attachment of ``domain``."""
        return self.env['ir.attachment'].search([('url', '=', f'{ROUTE}/{domain}')])

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_tool_results_become_capped_citable_sources(self):
        page = {
            'type': 'web',
            'url': 'https://www.a.test/p',
            'title': 'A',
            'content': 'x',
        }
        hits = [
            {'url': f'https://h.test/{index}', 'title': f'H{index}'}
            for index in range(15)
        ]
        rows = [
            {'id': 7, 'display_name': 'Acme'},
            {'id': 9, 'name': 'Beta'},
            {'id': 11},
            'junk',
        ]
        for name, arguments, result, sources in (
            ('web_fetch', {}, page, [('web:https://www.a.test/p', 'A')]),
            (
                'web_fetch',
                {},
                json.dumps(
                    {'type': 'web', 'url': 'https://www.b.test/x', 'title': None}
                ),
                [('web:https://www.b.test/x', 'b.test')],
            ),
            ('web_fetch', {}, {'url': 'https://a.test/x', 'error': 'HTTP 404'}, []),
            ('web_fetch', {}, {'type': 'web'}, []),
            ('web_fetch', {}, 'not json', []),
            (
                'web_search',
                {'query': 'q'},
                {'results': [*hits, {'title': 'no url'}]},
                [(f'web:https://h.test/{index}', f'H{index}') for index in range(10)],
            ),
            ('web_search', {'query': 'q'}, {'query': 'q', 'error': 'down'}, []),
            (
                'read_records',
                {'model': 'res.partner'},
                rows,
                [
                    ('record:res.partner,7', 'Acme'),
                    ('record:res.partner,9', 'Beta'),
                    ('record:res.partner,11', 'res.partner,11'),
                ],
            ),
            (
                'search_read',
                {'model': 'res.partner'},
                json.dumps([{'id': index} for index in range(1, 50)]),
                [
                    (f'record:res.partner,{index}', f'res.partner,{index}')
                    for index in range(1, 21)
                ],
            ),
            ('read_records', {}, rows, []),
            ('search_count', {'model': 'res.partner'}, {'count': 2}, []),
        ):
            with self.subTest(name=name, result=str(result)[:60]):
                self.assertEqual(
                    [
                        (source['id'], source.get('title') or source['display_name'])
                        for source in extract_sources(name, arguments, result)
                    ],
                    sources,
                )

    def test_web_icon_url_names_only_a_real_app_icon(self):
        for web_icon, url in (
            ('sale,static/description/icon.png', '/sale/static/description/icon.png'),
            (' sale , static/icon.png ', '/sale/static/icon.png'),
            ('base,static/description/icon.png', ''),
            ('fa fa-home,#FFFFFF,#875A7B', ''),
            ('sale,', ''),
            ('sale', ''),
            ('', ''),
            (False, ''),
        ):
            with self.subTest(web_icon=web_icon):
                self.assertEqual(web_icon_url(web_icon), url)

    def test_a_chat_turn_attaches_the_sources_of_each_tool_result(self):
        partner = self.env['res.partner'].create({'name': 'Acme'})
        agent = self.env['muk_ai.agent'].create({'name': 'Cited'})
        rate = self.env['res.currency.rate'].create(
            {'name': '2001-01-01', 'currency_id': self.env.ref('base.EUR').id}
        )
        session = self._session()
        page = {
            'https://www.a.test/notes': (200, {'Content-Type': 'text/plain'}, b'notes')
        }
        calls = [
            ('read_records', {'model': record._name, 'ids': record.ids})
            for record in (partner, agent, rate)
        ]
        calls += [
            ('web_fetch', {'url': 'https://www.a.test/notes'}),
            ('search_count', {'model': 'res.partner', 'domain': []}),
        ]
        with (
            serve_web(page),
            self._mock_responses([tool_payload(*calls), text_payload('done')]),
        ):
            session.send_message('cite your sources')
        sources = {
            event['call_id']: event.get('sources')
            for event in self._events(session, 'tool_result')
        }
        for call_id, record, icon in (
            ('call_1', partner, {'icon': '/muk_mcp/static/description/icon.png'}),
            ('call_2', agent, {'icon': '/muk_ai/static/description/icon.png'}),
            ('call_3', rate, {}),
        ):
            with self.subTest(model=record._name):
                self.assertEqual(
                    sources[call_id],
                    [
                        {
                            'id': f'record:{record._name},{record.id}',
                            'type': 'record',
                            'res_model': record._name,
                            'res_id': record.id,
                            'display_name': record.display_name,
                            'href': f'/odoo/{record._name}/{record.id}',
                            **icon,
                        }
                    ],
                )
        self.assertEqual(
            sources['call_4'],
            [
                {
                    'id': 'web:https://www.a.test/notes',
                    'type': 'web',
                    'url': 'https://www.a.test/notes',
                    'title': 'a.test',
                    'domain': 'a.test',
                    'icon': f'{ROUTE}/a.test',
                }
            ],
        )
        self.assertIsNone(sources['call_5'])

    def test_cited_domains_are_served_a_local_icon_fetched_once(self):
        vendor = 'https://imgs.search.brave.com/x/favicon.ico'
        page = (
            b'<html><head><link rel="icon" href="https://cdn.test/f.png"/></head>'
            b'<body><p>news</p></body></html>'
        )
        pages = {
            vendor: (200, {}, PNG_BYTES),
            'https://news.test/': (200, {'Content-Type': 'text/html'}, page),
            'https://cdn.test/f.png': (200, {}, PNG_BYTES),
        }
        with (
            serve_web(pages) as connections,
            self.assertNoLogs('odoo.tools.translate', 'WARNING'),
        ):
            first = self._search(
                ('https://www.a.test/1', vendor),
                ('https://a.test/2', None),
                ('https://b.test/3', None),
            )
            again = self._search(
                ('https://a.test/4', None), ('https://b.test/5', None), ('a.test', None)
            )
            fetched = self._tool('web_fetch', {'url': 'https://news.test/'})
        self.assertEqual(
            [connection['url'] for connection in connections],
            [
                vendor,
                'https://b.test/favicon.ico',
                'https://news.test/',
                'https://cdn.test/f.png',
            ],
        )
        hosts = ('a.test', 'a.test', 'b.test', 'a.test', 'b.test', None)
        self.assertEqual(
            [hit['icon'] for hit in first['results'] + again['results']],
            [host and f'{ROUTE}/{host}' for host in hosts],
        )
        self.assertEqual(fetched['icon'], f'{ROUTE}/news.test')
        self.assertNotRegex(
            json.dumps([first, again, fetched]), r'imgs\.search|cdn\.test'
        )
        self.assertEqual(self._icon('a.test').raw.content, PNG_BYTES)

    def test_the_icon_budget_leaves_late_domains_to_the_next_citation(self):
        targets = [(f'https://late{index}.test/', None) for index in range(3)]
        icons = [f'https://late{index}.test/favicon.ico' for index in range(3)]
        pages = {icon: (200, {}, PNG_BYTES) for icon in icons}
        with (
            serve_web(pages) as connections,
            patch(
                'odoo.addons.muk_ai.mcp.web.monotonic',
                side_effect=itertools.count(0, FAVICON_BUDGET / 2),
            ),
        ):
            result = self._search(*targets)
        with serve_web(pages) as later:
            self._search(*targets)
        self.assertEqual([connection['url'] for connection in connections], icons[:1])
        self.assertEqual([connection['url'] for connection in later], icons[1:])
        self.assertEqual(
            [hit['icon'] for hit in result['results']],
            [f'{ROUTE}/late{index}.test' for index in range(3)],
        )

    def test_the_vacuum_ages_out_icons_nothing_cited_lately(self):
        domains = ('aged.test', 'fresh.test', 'dead.test')
        icons = {
            f'https://{domain}/favicon.ico': (200, {}, PNG_BYTES)
            for domain in domains[:2]
        }
        with serve_web(icons):
            self._search(*[(f'https://{domain}/', None) for domain in domains])
        aged, fresh, dead = (self._icon(domain) for domain in domains)
        bystanders = self.env['ir.attachment'].create(
            [
                {'name': 'Near miss', 'url': f'{ROUTE}s/aged.test'},
                {
                    'name': 'Filed under a record',
                    'url': f'{ROUTE}/filed.test',
                    'res_model': 'res.partner',
                    'res_id': self.env.user.partner_id.id,
                },
                {'name': 'Plain file', 'datas': PNG_1x1},
            ]
        )
        self._backdate(
            aged | dead | bystanders, timedelta(days=FAVICON_MAX_AGE_DAYS + 1)
        )
        self._backdate(fresh, timedelta(days=FAVICON_MAX_AGE_DAYS - 1))
        self.assertEqual(self.env['muk_mcp.mixin']._gc_favicons(), (2, 0))
        self.assertEqual(
            (aged | fresh | dead | bystanders).exists(), fresh | bystanders
        )
        revived = {'https://dead.test/favicon.ico': (200, {}, PNG_BYTES)}
        with serve_web(revived) as connections:
            self._search(*[(f'https://{domain}/again', None) for domain in domains])
        self.assertEqual(
            [connection['url'] for connection in connections],
            ['https://aged.test/favicon.ico', 'https://dead.test/favicon.ico'],
        )
        self.assertEqual(self._icon('dead.test').raw.content, PNG_BYTES)

    def test_a_vacuum_reports_what_it_still_owes(self):
        aged = self.env['ir.attachment'].create(
            [
                {'name': f'Icon {index}', 'url': f'{ROUTE}/batch{index}.test'}
                for index in range(FAVICON_GC_BATCH + 1)
            ]
        )
        self._backdate(aged, timedelta(days=FAVICON_MAX_AGE_DAYS + 1))
        vacuum = self.env['muk_mcp.mixin']._gc_favicons
        self.assertEqual(vacuum(), (FAVICON_GC_BATCH, 1))
        self.assertEqual(vacuum(), (1, 0))
        self.assertFalse(aged.exists())


class TestSourceIconRoute(WebMixin, HttpCase):
    """Verify the icon route serves internal users only the real icons cited."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_route_serves_only_real_cached_icons_to_internal_users(self):
        new_test_user(self.env, login='icon-user')
        new_test_user(self.env, login='icon-portal', groups='base.group_portal')
        oversized = PNG_BYTES + bytes(FAVICON_MAX_BYTES)
        dns = {'img.hostile.test': ('127.0.0.1',)}
        png, ico = (PNG_BYTES, 'image/png'), (ICO_BYTES, 'image/vnd.microsoft.icon')
        for domain, status, body, login, served in (
            ('real.test', 200, PNG_BYTES, 'icon-user', png),
            ('real.test', None, None, 'icon-portal', None),
            ('ico.test', 200, ICO_BYTES, 'icon-user', ico),
            ('markup.test', 200, HTML_PAGE, 'icon-user', None),
            ('vector.test', 200, SVG_BYTES, 'icon-user', None),
            ('empty.test', 200, b'', 'icon-user', None),
            ('huge.test', 200, oversized, 'icon-user', None),
            ('dead.test', 404, b'', 'icon-user', None),
            ('hostile.test', 200, PNG_BYTES, 'icon-user', None),
            ('unknown.test', None, None, 'icon-user', None),
        ):
            with self.subTest(domain=domain, login=login):
                if status:
                    icon = f'https://img.{domain}/f'
                    head = f'<head><link rel="icon" href="{icon}"/></head>'
                    pages = {
                        f'https://{domain}/': (
                            200,
                            {},
                            f'<html>{head}</html>'.encode(),
                        ),
                        icon: (status, {'Content-Type': 'image/x-icon'}, body),
                    }
                    with serve_web(pages, dns) as connections:
                        self._tool('web_fetch', {'url': f'https://{domain}/'})
                    self.assertTrue(
                        all(
                            ipaddress.ip_address(c['ip']).is_global for c in connections
                        )
                    )
                self.authenticate(login, login)
                response = self.url_open(f'{ROUTE}/{domain}')
                self.assertEqual(response.status_code, 200 if served else 404)
                if served:
                    self.assertEqual(
                        (response.content, response.headers['Content-Type']), served
                    )
                    self.assertEqual(
                        response.headers['X-Content-Type-Options'], 'nosniff'
                    )
