from __future__ import annotations

import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase

from odoo.addons.muk_mcp.core.prompt import get_prompt_index, mcp_prompt
from odoo.addons.muk_mcp.core.registry import invalidate_registry_cache
from odoo.addons.muk_mcp.core.tool import mcp_tool


@mcp_prompt()
def auto_named(self) -> str:
    """First line is the description.

    More detail.
    """
    return ''


@mcp_prompt(name='summarize_record')
def _mcp_prompt_duplicate(self) -> str:
    """Clash with the name of the built-in prompt."""
    return ''


class TestMcpPrompt(TransactionCase):
    """Cover method, data and database prompts and argument completion."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Keep a handle on the prompt model."""
        super().setUpClass()
        cls.prompt_model = cls.env['muk_mcp.prompt']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _text(self, name: str, arguments: dict | None = None) -> str:
        """Render prompt ``name`` and return the text of its first message."""
        result = self.prompt_model.get_prompt(name, arguments)
        return result['messages'][0]['content']['text']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_listings_cover_method_and_data_prompts(self):
        listing = {prompt['name']: prompt for prompt in self.prompt_model.get_prompts()}
        self.assertEqual(
            [
                (arg['name'], arg['required'])
                for arg in listing['summarize_record']['arguments']
            ],
            [('model', True), ('record_id', True)],
        )
        self.assertEqual(listing['summarize_record']['title'], 'Summarize a record')
        self.assertNotIn('arguments', listing['activities_today'])
        kinds = {
            prompt['name']: prompt['kind']
            for prompt in self.prompt_model.get_playground_prompts()
        }
        self.assertEqual(
            (kinds['summarize_record'], kinds['activities_today']),
            ('method', 'db'),
        )

    def test_method_and_data_prompts_render(self):
        result = self.prompt_model.get_prompt(
            'summarize_record',
            {'model': 'res.partner', 'record_id': 7},
        )
        self.assertEqual(result['messages'][0]['role'], 'user')
        self.assertIn(
            "model='res.partner' and ids=[7]", result['messages'][0]['content']['text']
        )
        self.assertTrue(result['description'].startswith('Produce a concise'))
        self.assertIn('mail.activity', self._text('activities_today'))
        for name, arguments, message in (
            ('summarize_record', {'model': 'res.partner'}, 'Missing required'),
            (
                'summarize_record',
                {'model': 'x', 'record_id': 1, 'extra': 1},
                'Invalid arguments',
            ),
            ('no_such_prompt', {}, 'Prompt not found'),
        ):
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaisesRegex(UserError, message):
                    self.prompt_model.get_prompt(name, arguments)

    def test_database_prompts_render_and_shadow_methods(self):
        self.prompt_model.create(
            [
                {
                    'name': 'mcp_test_topic',
                    'title': 'Topic',
                    'description': 'Write about a topic.',
                    'arguments': json.dumps([{'name': 'topic', 'required': True}]),
                    'body': (
                        'result = "%s/%s" % (arguments["topic"], '
                        'env.context.get("mcp_probe"))\n'
                    ),
                },
                {
                    'name': 'mcp_test_messages',
                    'title': 'Messages',
                    'description': 'Return explicit messages.',
                    'body': (
                        'result = [{"role": "assistant", "content": "hello"}, '
                        '"skipped"]\n'
                    ),
                },
                {
                    'name': 'summarize_record',
                    'title': 'Override',
                    'description': 'Database override.',
                    'body': 'result = "from the database"\n',
                },
            ],
        )
        self.assertEqual(
            self._text(
                'mcp_test_topic', {'topic': 'invoices', 'context': {'mcp_probe': 'x'}}
            ),
            'invoices/x',
        )
        with self.assertRaisesRegex(UserError, 'Missing required'):
            self.prompt_model.get_prompt('mcp_test_topic', {})
        result = self.prompt_model.get_prompt('mcp_test_messages')
        self.assertEqual(
            result['messages'],
            [{'role': 'assistant', 'content': {'type': 'text', 'text': 'hello'}}],
        )
        self.assertEqual(self._text('summarize_record'), 'from the database')

    def test_prompt_definitions_are_validated(self):
        for values in (
            {'body': 'this is not python !!!'},
            {'arguments': '{not json'},
            {'arguments': json.dumps({'name': 'x'})},
        ):
            with self.subTest(values), self.assertRaises(ValidationError):
                self.prompt_model.create(
                    {
                        'name': 'mcp_test_bad',
                        'title': 'X',
                        'description': 'X',
                        **values,
                    },
                )

    def test_completion_suggests_model_names(self):
        prompt = {'type': 'ref/prompt', 'name': 'summarize_record'}
        values = self.prompt_model.complete_argument(
            prompt,
            {'name': 'model', 'value': 'res.par'},
        )['completion']['values']
        self.assertIn('res.partner', values)
        self.assertTrue(all(value.startswith('res.par') for value in values))
        everything = self.prompt_model.complete_argument(prompt, {'name': 'model'})
        self.assertEqual(len(everything['completion']['values']), 100)
        self.assertTrue(everything['completion']['hasMore'])
        for ref, argument in (
            (prompt, {'name': 'record_id', 'value': '1'}),
            (
                {'type': 'ref/resource', 'uri': 'odoo://x'},
                {'name': 'model', 'value': 'res'},
            ),
            (None, None),
        ):
            with self.subTest(ref=ref, argument=argument):
                self.assertEqual(
                    self.prompt_model.complete_argument(ref, argument),
                    {'completion': {'values': [], 'total': 0, 'hasMore': False}},
                )

    def test_decorators_default_from_the_function(self):
        tool = mcp_tool()(auto_named)
        for definition in (auto_named.__mcp_prompt__, tool.__mcp_tool__):
            self.assertEqual(
                (definition['name'], definition['description']),
                ('auto_named', 'First line is the description.'),
            )
        mixin_cls = type(self.env['muk_mcp.mixin'])
        mixin_cls._mcp_prompt_duplicate = _mcp_prompt_duplicate
        self.addCleanup(invalidate_registry_cache, self.env)
        self.addCleanup(delattr, mixin_cls, '_mcp_prompt_duplicate')
        invalidate_registry_cache(self.env)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            get_prompt_index(self.env)
