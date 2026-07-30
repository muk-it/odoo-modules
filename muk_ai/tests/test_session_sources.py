from __future__ import annotations

import json

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon
from odoo.addons.muk_ai.tools.sources import UNSET_MODULE_ICON, web_icon_url


class TestSessionSources(AITestCommon):
    """Verify tool-result events carry sources through to the client window."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _result_events(self, session: models.Model) -> list[dict]:
        """Return the ``tool_result`` events of ``session`` as the client sees them."""
        return [
            event
            for event in session.fetch_events()['events']
            if event.get('kind') == 'tool_result'
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_web_fetch_result_event_carries_web_source(self):
        session = self.env['muk_ai.session'].create({'name': 'Sources'})
        session._record_tool_result(
            [],
            'call-1',
            'web_fetch',
            json.dumps(
                {
                    'type': 'web',
                    'url': 'https://example.com/x',
                    'title': 'X',
                    'content': 'body',
                    'content_type': 'text/html',
                    'bytes': 4,
                },
                indent=2,
            ),
            arguments={'url': 'https://example.com/x'},
        )
        events = self._result_events(session)
        self.assertEqual(len(events), 1)
        sources = events[0].get('sources')
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['id'], 'web:https://example.com/x')
        self.assertEqual(sources[0]['type'], 'web')
        self.assertNotIn('content', sources[0])

    def test_read_records_result_event_carries_record_source(self):
        session = self.env['muk_ai.session'].create({'name': 'Sources'})
        session._record_tool_result(
            [],
            'call-2',
            'read_records',
            json.dumps([{'id': 5, 'display_name': 'Partner Five'}]),
            arguments={'model': 'res.partner', 'ids': [5]},
        )
        sources = self._result_events(session)[-1].get('sources')
        self.assertEqual(sources[0]['id'], 'record:res.partner,5')
        self.assertEqual(sources[0]['href'], '/odoo/res.partner/5')
        self.assertEqual(sources[0]['display_name'], 'Partner Five')

    def test_non_source_tool_result_has_no_sources_key(self):
        session = self.env['muk_ai.session'].create({'name': 'Sources'})
        session._record_tool_result(
            [],
            'call-3',
            'search_count',
            '{"count": 2}',
            arguments={'model': 'res.partner'},
        )
        self.assertNotIn('sources', self._result_events(session)[-1])

    def test_record_source_carries_the_resolved_app_icon(self):
        session = self.env['muk_ai.session'].create({'name': 'Sources'})
        session._record_tool_result(
            [],
            'call-4',
            'read_records',
            json.dumps([{'id': 5, 'display_name': 'Partner Five'}]),
            arguments={'model': 'res.partner', 'ids': [5]},
        )
        source = self._result_events(session)[-1]['sources'][0]
        expected = self.env['ir.model']._ai_source_icons().get('res.partner')
        self.assertEqual(source.get('icon'), expected)

    def test_web_source_carries_no_app_icon(self):
        session = self.env['muk_ai.session'].create({'name': 'Sources'})
        session._record_tool_result(
            [],
            'call-5',
            'web_fetch',
            json.dumps({'type': 'web', 'url': 'https://example.com/x', 'title': 'X'}),
            arguments={'url': 'https://example.com/x'},
        )
        self.assertNotIn('icon', self._result_events(session)[-1]['sources'][0])


class TestSourceAppIcons(AITestCommon):
    """Verify a record source resolves to its app icon, never the placeholder."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_web_icon_url_rejects_the_placeholder_and_malformed_values(self):
        self.assertEqual(
            web_icon_url('point_of_sale,static/description/icon.png'),
            '/point_of_sale/static/description/icon.png',
        )
        self.assertEqual(web_icon_url('base,static/description/icon.png'), '')
        self.assertEqual(web_icon_url('no_comma'), '')
        self.assertEqual(web_icon_url(''), '')

    def test_web_icon_url_rejects_a_studio_built_icon(self):
        self.assertEqual(web_icon_url('fa fa-home,#FFFFFF,#875A7B'), '')
        self.assertEqual(web_icon_url('module,'), '')

    def test_resolver_never_offers_the_placeholder(self):
        icons = self.env['ir.model']._ai_source_icons()
        self.assertTrue(icons)
        self.assertNotIn(UNSET_MODULE_ICON, set(icons.values()))

    def test_prefix_module_icon_wins_over_the_app_menu(self):
        model = self.env['ir.model']
        by_module = model._ai_module_icons()
        for name, icon in model._ai_source_icons().items():
            if expected := by_module.get(name.split('.')[0]):
                self.assertEqual(icon, expected, name)

    def test_app_menu_resolves_models_the_prefix_cannot(self):
        model = self.env['ir.model']
        by_module = model._ai_module_icons()
        resolved = model._ai_source_icons()
        self.assertTrue(
            [n for n in resolved if n.split('.')[0] not in by_module],
            'the app-menu layer contributed nothing',
        )
