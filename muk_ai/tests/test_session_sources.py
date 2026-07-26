from __future__ import annotations

import json

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon


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
