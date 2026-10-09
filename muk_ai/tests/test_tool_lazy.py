from __future__ import annotations

import json
from contextlib import AbstractContextManager
from unittest.mock import patch

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload
from odoo.addons.muk_ai.tools.call import (
    format_tool_signature,
    summarize_tool_description,
)

CATALOG = (
    {
        'name': 'list_models',
        'description': 'List installed models.',
        'inputSchema': {'type': 'object'},
    },
    {
        'name': 'rare_tool',
        'description': 'Rarely used. Takes one argument.',
        'inputSchema': {
            'type': 'object',
            'properties': {'x': {'type': 'string'}},
            'required': ['x'],
        },
    },
    {
        'name': 'another_rare',
        'description': 'Also rare',
        'inputSchema': {'type': 'object'},
    },
    {
        'name': 'server.rare_tool',
        'description': 'Namespaced tool',
        'inputSchema': {'type': 'object'},
    },
    {'name': 'bare_tool'},
    {
        'name': 'generate_image',
        'description': 'Generate an image',
        'inputSchema': {'type': 'object'},
    },
)


class TestToolLazy(AITestCommon):
    """Verify the chat ships essential tools and loads the rest on demand."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Add an agent with one essential tool."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create(
            {'name': 'Lazy', 'essential_tool_names': ['list_models']}
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _patch_catalog(self) -> AbstractContextManager:
        """Serve the test catalogue in place of the registered tools."""
        return patch.object(
            type(self.env['muk_mcp.tool']),
            'get_tools',
            lambda self_arg, registry=None: [dict(entry) for entry in CATALOG],
        )

    def _load(
        self, arguments: dict, agent: models.BaseModel | None = None
    ) -> tuple[models.BaseModel, list]:
        """Run a turn whose first round calls ``tool_load``, return chat and executions."""
        session = self._session(agent_id=(agent or self.agent).id)
        with (
            self._patch_catalog(),
            self._patch_tool({'rare_tool': {'called': True}}) as executed,
            self._mock_responses(
                [tool_payload(('tool_load', arguments, 'c1')), text_payload()]
            ),
        ):
            session.start('load a tool')
        return session, executed

    def _listed(self, request: dict) -> list[str]:
        """Return the lines of the ``<available_tools>`` block naming a tool."""
        text = self._system_prompt(request)
        block = text.partition('<available_tools>')[2].partition('</available_tools>')
        names = tuple(entry['name'] for entry in CATALOG)
        return [line for line in block[0].splitlines() if line.startswith(names)]

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_deferred_tool_is_summarized_in_one_line(self):
        for function, value, expected in (
            (
                format_tool_signature,
                (
                    'export_records',
                    {
                        'properties': {'model': {}, 'fields': {}, 'limit': {}},
                        'required': ['model', 'fields'],
                    },
                ),
                'export_records(model*, fields*, limit)',
            ),
            (format_tool_signature, ('whoami', {'type': 'object'}), 'whoami'),
            (format_tool_signature, ('whoami', None), 'whoami'),
            (format_tool_signature, ('tool', {'properties': 5}), 'tool'),
            (format_tool_signature, ('tool', {'properties': 'xy'}), 'tool'),
            (format_tool_signature, ('tool', 'garbage'), 'tool'),
            (
                format_tool_signature,
                ('tool', {'properties': {'model': {}}, 'required': 'model'}),
                'tool(model)',
            ),
            (
                summarize_tool_description,
                ('Export records. Field paths use "/".',),
                'Export records.',
            ),
            (
                summarize_tool_description,
                ('Fetch a\n  resource\tby uri',),
                'Fetch a resource by uri',
            ),
            (
                summarize_tool_description,
                ('word ' * 200,),
                ' '.join(['word'] * 23) + '...',
            ),
            (
                summarize_tool_description,
                ('x' * 40 + ' ' + 'y' * 300 + '. Tail.',),
                'x' * 40 + '...',
            ),
            (summarize_tool_description, (None,), ''),
        ):
            with self.subTest(function=function.__name__, value=value):
                self.assertEqual(function(*value), expected)

    def test_the_first_request_ships_the_essentials_and_lists_the_rest(self):
        image_model = self._create_model('lazy-image', modality='image')
        everything = ['list_models', 'rare_tool', 'another_rare', 'server.rare_tool']
        deferred = [
            'another_rare: Also rare',
            'bare_tool',
            'rare_tool(x*): Rarely used.',
            'server.rare_tool: Namespaced tool',
        ]
        for values, tools, listed in (
            ({}, {'list_models', 'tool_load', 'ask_user'}, deferred),
            (
                {
                    'essential_tool_names': ['list_models', 'rare_tool', 'missing'],
                    'tool_filter': ['list_models', 'another_rare'],
                },
                {'list_models', 'tool_load', 'ask_user'},
                ['another_rare: Also rare'],
            ),
            (
                {
                    'essential_tool_names': [*everything, 'bare_tool'],
                    'tool_filter': [*everything, 'bare_tool'],
                },
                {*everything, 'bare_tool', 'ask_user'},
                [],
            ),
            (
                {'enable_image_generation': True, 'image_model_id': image_model.id},
                {'list_models', 'generate_image', 'tool_load', 'ask_user'},
                deferred,
            ),
        ):
            with (
                self.subTest(values=values),
                self._patch_catalog(),
                self._mock_responses([text_payload()]) as requests,
            ):
                self._session(agent_id=self.agent.copy(values).id).start('hello')
                names = self._tools(requests[0])
                self.assertEqual(names, tools)
                self.assertEqual(self._listed(requests[0]), listed)

    def test_tool_load_resolves_what_the_chat_may_call(self):
        filtered = self.agent.copy({'tool_filter': ['list_models']})
        for arguments, agent, loaded, unknown, error in (
            ({'names': ['rare_tool']}, None, ['rare_tool'], [], False),
            ({'names': ['no_such_tool']}, None, [], ['no_such_tool'], True),
            ({'names': ['rare_tool', 'nope']}, None, ['rare_tool'], ['nope'], False),
            ({'names': ['functions.rare_tool']}, None, ['rare_tool'], [], False),
            ({'names': ['server.rare_tool']}, None, ['server.rare_tool'], [], False),
            (
                {'names': ['rare_tool', ' rare_tool ', 'another_rare']},
                None,
                ['rare_tool', 'another_rare'],
                [],
                False,
            ),
            ({'names': ['rare_tool']}, filtered, [], ['rare_tool'], True),
            ({'names': []}, None, [], [], True),
            ({'names': 'rare_tool'}, None, [], [], True),
            ({}, None, [], [], True),
        ):
            with self.subTest(arguments=arguments, filtered=bool(agent)):
                session, _executed = self._load(arguments, agent)
                output = self._tool_output(session, 'c1')
                self.assertEqual(
                    (list(output.get('loaded', [])), output.get('unknown', [])),
                    (loaded, unknown),
                )
                self.assertEqual('error' in output, error)
                self.assertEqual(session.expanded_tool_names or [], loaded)

    def test_tool_load_can_run_one_of_the_loaded_tools_inline(self):
        for call, names, executed in (
            (
                {'name': 'functions.rare_tool', 'arguments': {'x': '1'}},
                ['functions.rare_tool'],
                [('rare_tool', {'x': '1'})],
            ),
            (
                {'name': 'rare_tool', 'x': '2'},
                ['rare_tool'],
                [('rare_tool', {'x': '2'})],
            ),
            ({'name': 'list_models', 'arguments': {}}, ['rare_tool'], []),
            ({'arguments': {'x': '3'}}, ['rare_tool'], []),
            ({'name': 'rare_tool', 'arguments': 'x=4'}, ['rare_tool'], []),
            ('rare_tool', ['rare_tool'], []),
        ):
            with self.subTest(call=call):
                session, calls = self._load({'names': names, 'call': call})
                inline = self._tool_output(session, 'c1')['call']
                self.assertEqual(
                    [(item['name'], item['arguments']) for item in calls], executed
                )
                self.assertEqual('error' in inline, not executed)
                if executed:
                    self.assertEqual(
                        (inline['name'], json.loads(inline['output'])),
                        ('rare_tool', {'called': True}),
                    )
                    self.assertIn(
                        'rare_tool',
                        [
                            event['name']
                            for event in self._events(session, 'tool_result')
                        ],
                    )

    def test_a_deferred_tool_runs_once_tool_load_loaded_it(self):
        session = self._session(agent_id=self.agent.id)
        with (
            self._patch_catalog(),
            self._patch_tool({'rare_tool': {'called': True}}) as executed,
            self._mock_responses(
                [
                    tool_payload(('tool_load', {'names': ['rare_tool']}, 'c1')),
                    tool_payload(('rare_tool', {'x': 'hello'}, 'c2')),
                    text_payload('done'),
                ]
            ) as requests,
        ):
            session.start('use the rare tool')
        first, second = (self._tools(r) for r in requests[:2])
        self.assertNotIn('rare_tool', first)
        self.assertIn('rare_tool(x*): Rarely used.', self._listed(requests[0]))
        self.assertIn('rare_tool', second)
        self.assertNotIn('rare_tool(x*): Rarely used.', self._listed(requests[1]))
        self.assertEqual(
            [(call['name'], call['arguments']) for call in executed],
            [('rare_tool', {'x': 'hello'})],
        )
        self.assertEqual(self._tool_output(session, 'c2'), {'called': True})
        self.assertEqual(session.state, 'done')
