from __future__ import annotations

import json

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload

RECORD = {
    'kind': 'record',
    'model': 'res.partner',
    'id': 42,
    'display_name': 'ACME Corp',
}


class TestViewContext(AITestCommon):
    """Verify the view a chat is pinned to reaches the model on every request."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the partner and the action the navigation tools open."""
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Pinned Partner'})
        cls.action = cls.env.ref('base.action_partner_form')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _call(self, name: str, arguments: dict) -> dict:
        """Run a navigation tool as an MCP client does and decode its result."""
        text, _info = self.env['muk_mcp.tool']._call(name, arguments, self.env)
        return json.loads(text)

    def _ui_ctx(self, request: dict) -> list[str]:
        """Return the ``<ui_ctx>`` texts a provider request carries."""
        return [
            block['text']
            for item in request['inputs']
            if isinstance(item.get('content'), list)
            for block in item['content']
            if str(block.get('text', '')).startswith('<ui_ctx>')
        ]

    def _view_context_events(self, bus: list) -> list:
        """Return the view contexts broadcast to the chat clients."""
        return [
            message['payload']['view_context']
            for _target, kind, message in bus
            if kind == 'muk_ai.event' and message['type'] == 'view_context'
        ]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_pinned_view_is_cleaned_and_rendered_for_the_model(self):
        domain = [['is_company', '=', True]]
        listing = {'kind': 'list', 'model': 'res.partner', 'view_type': 'kanban'}
        action = {'kind': 'action', 'model': 'res.partner', 'action_id': 42}
        pivot = {
            'kind': 'pivot',
            'model': 'res.partner',
            'pivot_measures': ['credit'],
            'pivot_row_groupby': ['country_id'],
            'pivot_column_groupby': ['user_id'],
            'domain': domain,
        }
        graph = {
            'kind': 'graph',
            'model': 'res.partner',
            'graph_mode': 'bar',
            'graph_measure': 'credit',
            'graph_groupbys': ['country_id'],
        }
        for payload, pinned, segments in (
            ({**RECORD, 'stray': 1}, RECORD, ['res.partner/42', '"ACME Corp"']),
            (
                {**listing, 'domain': domain},
                {**listing, 'domain': domain},
                ['res.partner', 'kanban', 'domain=[["is_company","=",true]]'],
            ),
            (
                {'kind': 'list', 'model': 'res.partner', 'domain': []},
                {**listing, 'view_type': 'list'},
                ['res.partner', 'list'],
            ),
            (action, action, ['action', 'id=42', 'res.partner']),
            (
                pivot,
                {**pivot, 'view_type': 'pivot'},
                ['pivot', 'measures=credit', 'rows=country_id', 'domain=[["is_'],
            ),
            (
                graph,
                {**graph, 'view_type': 'graph'},
                ['graph', 'mode=bar', 'measure=credit', 'groupbys=country_id'],
            ),
            (None, None, None),
            ({'kind': 'none'}, None, None),
        ):
            with self.subTest(payload=payload):
                session = self._session()
                session.set_view_context(RECORD)
                snapshot = session.set_view_context(payload)
                self.assertEqual(snapshot['view_context'], pinned)
                with self._mock_responses([text_payload()]) as requests:
                    session.start('what am I looking at?')
                tags = self._ui_ctx(requests[0])
                self.assertEqual(len(tags), int(bool(pinned)))
                for segment in segments or ():
                    self.assertIn(segment, tags[0])
                if pinned:
                    self.assertEqual(
                        requests[0]['inputs'][-1]['content'][0]['text'], tags[0]
                    )
                self.assertNotIn('<ui_ctx>', json.dumps(session.conversation))

    def test_a_malformed_view_context_is_refused(self):
        session = self._session()
        session.set_view_context(RECORD)
        for payload in (
            'record',
            {'model': 'res.partner'},
            {'kind': 'banana'},
            {'kind': '_cleaners'},
            {**RECORD, 'id': -1},
            {**RECORD, 'id': '42'},
            {**RECORD, 'display_name': 5},
            {**RECORD, 'ee_init_context': [1]},
            {'kind': 'list', 'model': 42},
            {'kind': 'list', 'model': 'res.partner', 'domain': 'oops'},
            {'kind': 'action', 'action_id': 'x'},
            {'kind': 'pivot', 'pivot_measures': 'oops'},
            {'kind': 'graph', 'graph_groupbys': ['ok', 1]},
            {'kind': 'graph', 'graph_mode': 123},
        ):
            with self.subTest(payload=payload), self.assertRaises(UserError):
                session.set_view_context(payload)
        self.assertEqual(session.view_context, RECORD)

    def test_unpinning_clears_the_view_and_says_so(self):
        session = self._session()
        session.set_view_context(RECORD)
        with self._capture_bus() as bus:
            snapshot = session.unpin_view_context()
        self.assertIsNone(snapshot['view_context'])
        self.assertEqual(self._view_context_events(bus), [None])
        last = self._events(session)[-1]
        self.assertEqual((last['kind'], last['name']), ('command', '/unpin'))

    def test_a_navigation_tool_returns_the_action_to_dispatch(self):
        for name, arguments, expected in (
            (
                'open_view',
                {'model': 'res.partner'},
                {
                    'type': 'ir.actions.act_window',
                    'res_model': 'res.partner',
                    'view_mode': 'list',
                    'domain': [],
                    'context': None,
                },
            ),
            (
                'open_view',
                {
                    'model': 'res.partner',
                    'view_type': 'tree',
                    'name': 'My Partners',
                    'domain': '[["is_company", "=", true]]',
                    'additional_context': {},
                },
                {
                    'view_mode': 'list',
                    'name': 'My Partners',
                    'domain': [['is_company', '=', True]],
                    'context': None,
                },
            ),
            (
                'open_view',
                {
                    'model': 'res.partner',
                    'view_type': 'graph',
                    'additional_context': {'graph_mode': 'bar'},
                },
                {
                    'view_mode': 'graph',
                    'views': [[False, 'graph']],
                    'context': {'graph_mode': 'bar'},
                },
            ),
            ('open_view', {'model': 'res.partner', 'view_type': 'bogus'}, UserError),
            ('open_view', {'model': 'res.partner', 'target': 'bogus'}, UserError),
            (
                'open_record',
                {'model': 'res.partner', 'res_id': self.partner.id},
                {
                    'type': 'ir.actions.act_window',
                    'res_id': self.partner.id,
                    'view_mode': 'form',
                    'target': 'current',
                },
            ),
            (
                'open_record',
                {
                    'model': 'res.partner',
                    'res_id': self.partner.id,
                    'view_type': 'kanban',
                    'target': 'new',
                },
                {'view_mode': 'kanban', 'target': 'new'},
            ),
            (
                'open_action',
                {'action_ref': 'base.action_partner_form'},
                {'res_model': 'res.partner', 'id': self.action.id},
            ),
            ('open_action', {'action_ref': self.action.id}, {'id': self.action.id}),
            (
                'open_action',
                {'action_ref': str(self.action.id)},
                {'id': self.action.id},
            ),
            ('open_action', {'action_ref': 'nothing_here'}, UserError),
            ('open_action', {'action_ref': 'base.main_company'}, UserError),
            ('open_action', {'action_ref': 999999999}, UserError),
            (
                'show_notification',
                {'message': 'Hello'},
                {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {'message': 'Hello', 'type': 'info', 'sticky': False},
                },
            ),
            (
                'show_notification',
                {'message': 'Saved', 'title': 'Done', 'type': 'success', 'sticky': 1},
                {
                    'params': {
                        'message': 'Saved',
                        'title': 'Done',
                        'type': 'success',
                        'sticky': True,
                    },
                },
            ),
        ):
            with self.subTest(name=name, arguments=arguments):
                if isinstance(expected, type):
                    with self.assertRaises(expected):
                        self._call(name, arguments)
                else:
                    result = self._call(name, arguments)
                    self.assertEqual(
                        {key: result.get(key) for key in expected}, expected
                    )
        result = self._call(
            'open_action',
            {'action_ref': self.action.id, 'additional_context': {'default_name': 'X'}},
        )
        self.assertEqual(
            result['context'],
            {'res_partner_search_mode': 'customer', 'default_name': 'X'},
        )

    def test_the_pin_follows_where_the_agent_navigates(self):
        for name, arguments, pinned in (
            (
                'open_record',
                {'model': 'res.partner', 'res_id': self.partner.id},
                {
                    'kind': 'record',
                    'model': 'res.partner',
                    'id': self.partner.id,
                    'display_name': 'Pinned Partner',
                },
            ),
            (
                'open_view',
                {
                    'model': 'res.partner',
                    'view_type': 'kanban',
                    'domain': '[["is_company", "=", true]]',
                },
                {
                    'kind': 'list',
                    'model': 'res.partner',
                    'view_type': 'kanban',
                    'domain': [['is_company', '=', True]],
                },
            ),
            (
                'open_action',
                {'action_ref': 'base.action_partner_form'},
                {'kind': 'action', 'model': 'res.partner', 'action_id': self.action.id},
            ),
            ('show_notification', {'message': 'Done'}, {}),
        ):
            with self.subTest(name=name):
                session = self._session()
                with (
                    self._capture_bus() as bus,
                    self._mock_responses(
                        [tool_payload((name, arguments, 'c1')), text_payload('there')]
                    ) as requests,
                ):
                    session.start('take me there')
                actions = [
                    message['payload']
                    for _target, kind, message in bus
                    if kind == 'muk_ai.event' and message['type'] == 'ui_action'
                ]
                self.assertEqual([action['name'] for action in actions], [name])
                self.assertEqual(
                    actions[0]['action'],
                    self._tool_output(session, 'c1'),
                )
                context = session.view_context or {}
                self.assertEqual({key: context.get(key) for key in pinned}, pinned)
                self.assertEqual(bool(context), bool(pinned))
                self.assertEqual(len(self._view_context_events(bus)), int(bool(pinned)))
                self.assertEqual(len(self._ui_ctx(requests[1])), int(bool(pinned)))

    def test_a_write_tool_on_a_chat_pinned_to_a_record_tells_its_screens(self):
        partner = {'model': 'res.partner', 'id': self.partner.id}
        record = {'kind': 'record', **partner}
        listing = {'kind': 'list', 'model': 'res.partner', 'view_type': 'list'}
        note = {**partner, 'body': 'Called'}
        read = {'model': 'res.partner', 'ids': [self.partner.id]}
        for pinned, name, arguments, written in (
            (record, 'post_message', note, [partner]),
            (record, 'read_records', read, []),
            (listing, 'post_message', note, []),
        ):
            with self.subTest(pinned=pinned['kind'], name=name):
                session = self._session()
                session.set_view_context(pinned)
                with (
                    self._capture_bus() as bus,
                    self._mock_responses(
                        [tool_payload((name, arguments, 'c1')), text_payload('done')]
                    ),
                ):
                    session.start('log the call')
                self.assertEqual(
                    [
                        message['payload']
                        for _target, kind, message in bus
                        if kind == 'muk_ai.event'
                        and message['type'] == 'record_written'
                    ],
                    written,
                )
