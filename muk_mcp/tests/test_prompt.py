import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import common, tagged

from odoo.addons.muk_mcp.core import prompt as core_prompt
from odoo.addons.muk_mcp.tools import protocol


@tagged('post_install', '-at_install')
class TestMcpPrompt(common.TransactionCase):
    """Cover the prompt decorator, built-in, completion and DB-defined prompt paths."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.prompt_model = cls.env['muk_mcp.prompt']

    # ----------------------------------------------------------
    # Tests — decorator / registry
    # ----------------------------------------------------------

    def test_decorator_stamps_metadata(self):
        @core_prompt.mcp_prompt(
            name='dummy',
            title='Dummy',
            description='Does nothing.',
            arguments=[{'name': 'x', 'required': True}],
        )
        def handler(self, x=None):
            return None

        self.assertEqual(handler.__mcp_prompt__['name'], 'dummy')
        self.assertEqual(handler.__mcp_prompt__['title'], 'Dummy')
        self.assertEqual(handler.__mcp_prompt__['description'], 'Does nothing.')
        self.assertEqual(
            handler.__mcp_prompt__['arguments'],
            [{'name': 'x', 'required': True}],
        )

    def test_decorator_infers_name_and_description(self):
        @core_prompt.mcp_prompt()
        def auto_named(self):
            """First line is the description.

            More detail ignored.
            """
            return

        self.assertEqual(auto_named.__mcp_prompt__['name'], 'auto_named')
        self.assertEqual(
            auto_named.__mcp_prompt__['description'],
            'First line is the description.',
        )

    def test_registry_rejects_duplicate_prompt_name(self):
        mixin_cls = type(self.env['muk_mcp.mixin'])

        @core_prompt.mcp_prompt(name='summarize_record')
        def _mcp_prompt_dupe(self):
            return 'dupe'

        mixin_cls._mcp_prompt_dupe = _mcp_prompt_dupe
        core_prompt.invalidate_prompt_cache(self.env)
        try:
            with self.assertRaises(ValueError):
                core_prompt.get_prompt_index(self.env)
        finally:
            delattr(mixin_cls, '_mcp_prompt_dupe')
            core_prompt.invalidate_prompt_cache(self.env)

    # ----------------------------------------------------------
    # Tests — built-in (method) prompts
    # ----------------------------------------------------------

    def test_get_prompts_lists_builtin_prompts(self):
        names = [entry['name'] for entry in self.prompt_model.get_prompts()]
        self.assertIn('summarize_record', names)

    def test_get_playground_prompts_exposes_kind_and_arguments(self):
        by_name = {
            entry['name']: entry for entry in self.prompt_model.get_playground_prompts()
        }
        self.assertIn('summarize_record', by_name)
        self.assertEqual(by_name['summarize_record']['kind'], 'method')
        self.assertIn('activities_today', by_name)
        self.assertEqual(by_name['activities_today']['kind'], 'db')
        for entry in by_name.values():
            self.assertIn('title', entry)
            self.assertIn('description', entry)
            self.assertIsInstance(entry['arguments'], list)

    def test_get_prompts_lists_xml_data_prompt(self):
        names = [entry['name'] for entry in self.prompt_model.get_prompts()]
        self.assertIn('activities_today', names)

    def test_get_prompt_runs_xml_data_prompt(self):
        result = self.prompt_model.get_prompt('activities_today', {})
        text = result['messages'][0]['content']['text']
        self.assertIn('mail.activity', text)
        self.assertIn('whoami', text)

    def test_get_prompts_exposes_arguments(self):
        by_name = {entry['name']: entry for entry in self.prompt_model.get_prompts()}
        summarize = by_name['summarize_record']
        arg_names = {arg['name'] for arg in summarize['arguments']}
        self.assertEqual(arg_names, {'model', 'record_id'})
        required = {
            arg['name'] for arg in summarize['arguments'] if arg.get('required')
        }
        self.assertEqual(required, {'model', 'record_id'})

    def test_get_prompt_returns_messages(self):
        result = self.prompt_model.get_prompt(
            'summarize_record',
            {'model': 'res.partner', 'record_id': '7'},
        )
        self.assertIn('messages', result)
        self.assertEqual(len(result['messages']), 1)
        message = result['messages'][0]
        self.assertEqual(message['role'], 'user')
        self.assertEqual(message['content']['type'], 'text')
        self.assertIn('res.partner', message['content']['text'])
        self.assertIn('7', message['content']['text'])

    def test_get_prompt_missing_required_argument_raises(self):
        with self.assertRaises(UserError):
            self.prompt_model.get_prompt(
                'summarize_record',
                {'model': 'res.partner'},
            )

    def test_get_prompt_unknown_raises(self):
        with self.assertRaises(UserError):
            self.prompt_model.get_prompt('does_not_exist', {})

    # ----------------------------------------------------------
    # Tests — completion
    # ----------------------------------------------------------

    def test_complete_argument_completes_model_names(self):
        result = self.prompt_model.complete_argument(
            {'type': 'ref/prompt', 'name': 'summarize_record'},
            {'name': 'model', 'value': 'res.par'},
        )
        values = result['completion']['values']
        self.assertIn('res.partner', values)
        self.assertTrue(all(v.startswith('res.par') for v in values))

    def test_complete_argument_unknown_field_returns_empty(self):
        result = self.prompt_model.complete_argument(
            {'type': 'ref/prompt', 'name': 'summarize_record'},
            {'name': 'record_id', 'value': '1'},
        )
        self.assertEqual(result['completion']['values'], [])
        self.assertEqual(result['completion']['total'], 0)
        self.assertFalse(result['completion']['hasMore'])

    def test_complete_argument_non_prompt_ref_returns_empty(self):
        result = self.prompt_model.complete_argument(
            {'type': 'ref/resource', 'uri': 'odoo://x'},
            {'name': 'model', 'value': 'res'},
        )
        self.assertEqual(result['completion']['values'], [])

    def test_initialize_result_advertises_prompt_and_completion(self):
        caps = protocol.make_initialize_result()['capabilities']
        self.assertIn('prompts', caps)
        self.assertEqual(caps['prompts'], {'listChanged': True})
        self.assertIn('completions', caps)

    # ----------------------------------------------------------
    # Tests — database (UI) prompts
    # ----------------------------------------------------------

    def test_db_prompt_listed_and_run(self):
        self.prompt_model.create(
            {
                'name': 'mcp_test_db_prompt',
                'title': 'DB prompt',
                'description': 'A database-defined prompt.',
                'arguments': json.dumps(
                    [
                        {'name': 'topic', 'required': True},
                    ],
                ),
                'body': "result = 'Write about %s' % arguments['topic']\n",
            },
        )
        names = [entry['name'] for entry in self.prompt_model.get_prompts()]
        self.assertIn('mcp_test_db_prompt', names)
        result = self.prompt_model.get_prompt(
            'mcp_test_db_prompt',
            {'topic': 'invoices'},
        )
        text = result['messages'][0]['content']['text']
        self.assertEqual(text, 'Write about invoices')

    def test_db_prompt_can_return_message_list(self):
        self.prompt_model.create(
            {
                'name': 'mcp_test_db_messages',
                'title': 'DB messages',
                'description': 'Returns explicit messages.',
                'body': ("result = [{'role': 'user', 'content': 'hello'}]\n"),
            },
        )
        result = self.prompt_model.get_prompt('mcp_test_db_messages', {})
        message = result['messages'][0]
        self.assertEqual(message['role'], 'user')
        self.assertEqual(message['content']['type'], 'text')
        self.assertEqual(message['content']['text'], 'hello')

    def test_db_prompt_missing_required_argument_raises(self):
        self.prompt_model.create(
            {
                'name': 'mcp_test_db_required',
                'title': 'DB required',
                'description': 'Requires an argument.',
                'arguments': json.dumps([{'name': 'topic', 'required': True}]),
                'body': "result = arguments.get('topic') or ''\n",
            },
        )
        with self.assertRaises(UserError):
            self.prompt_model.get_prompt('mcp_test_db_required', {})

    def test_db_prompt_shadows_builtin(self):
        self.prompt_model.create(
            {
                'name': 'summarize_record',
                'title': 'DB summarize override',
                'description': 'DB override of the builtin summarize prompt.',
                'arguments': json.dumps(
                    [
                        {'name': 'model', 'required': True},
                        {'name': 'record_id', 'required': True},
                    ],
                ),
                'body': "result = 'DB summary for %s' % arguments['model']\n",
            },
        )
        result = self.prompt_model.get_prompt(
            'summarize_record',
            {'model': 'res.partner', 'record_id': '1'},
        )
        text = result['messages'][0]['content']['text']
        self.assertEqual(text, 'DB summary for res.partner')

    def test_db_prompt_invalid_code_rejected(self):
        with self.assertRaises(ValidationError):
            self.prompt_model.create(
                {
                    'name': 'mcp_test_bad_code',
                    'title': 'Bad code',
                    'description': 'Invalid python.',
                    'body': 'this is not valid python !!!\n',
                },
            )

    def test_db_prompt_invalid_arguments_json_rejected(self):
        with self.assertRaises(ValidationError):
            self.prompt_model.create(
                {
                    'name': 'mcp_test_bad_args',
                    'title': 'Bad args',
                    'description': 'Invalid arguments JSON.',
                    'arguments': '{not json',
                    'body': "result = ''\n",
                },
            )

    def test_db_prompt_arguments_must_be_list(self):
        with self.assertRaises(ValidationError):
            self.prompt_model.create(
                {
                    'name': 'mcp_test_args_not_list',
                    'title': 'Args not list',
                    'description': 'Arguments is an object, not an array.',
                    'arguments': json.dumps({'name': 'x'}),
                    'body': "result = ''\n",
                },
            )
