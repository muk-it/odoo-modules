from __future__ import annotations

from typing import Any
from unittest.mock import PropertyMock, patch

from odoo import models

from odoo.addons.muk_mcp.tests.common import MCPHttpCase, make_mcp_key
from odoo.addons.muk_mcp_access.models.confirmation import MCPAccessConfirmation


class TestConfirmation(MCPHttpCase):
    """Ask the user before a client changes a model that wants to be asked for."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Let clients change partners and tags, and ask before the first."""
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Before'})
        cls.entry = cls.allow('res.partner', confirm=True)
        cls.allow('res.partner.category')
        cls.update = {
            'model': 'res.partner',
            'ids': [cls.partner.id],
            'values': {'name': 'After'},
        }

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def allow(cls, model: str, confirm: bool = False) -> models.BaseModel:
        """Let clients read and change a model."""
        return cls.env['muk_mcp_access.model'].create(
            {
                'model_id': cls.env['ir.model']._get_id(model),
                'allow_write': True,
                'confirm_write': confirm,
            }
        )

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        state: Any = None,
        response: Any = None,
        capabilities: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call a tool as a client that can ask, with the answer of a retry."""
        params = {'name': name, 'arguments': arguments}
        if state:
            params['requestState'] = state
        if response:
            params['inputResponses'] = {'confirm': response}
        if capabilities is None:
            capabilities = {'elicitation': {}}
        meta = self.mcp_meta(capabilities)
        return self.mcp_stateless_post('tools/call', params, meta=meta, **kwargs)

    def ask(self, arguments: dict[str, Any] | None = None, **kwargs: Any) -> str:
        """Call the update tool, assert it asks first and return the state."""
        result = self.call('update_records', arguments or self.update, **kwargs).json()[
            'result'
        ]
        self.assertEqual(result['resultType'], 'input_required')
        self.assertEqual(self.partner.name, 'Before')
        return result['requestState']

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_an_accepted_change_is_written_once(self):
        arguments = {'model': 'res.partner', 'values': {'name': 'Once'}}
        created = [('name', '=', 'Once')]
        result = self.call('create_records', arguments).json()['result']
        self.assertEqual(result['resultType'], 'input_required')
        question = result['inputRequests']['confirm']
        self.assertEqual(question['method'], 'elicitation/create')
        self.assertIn('create_records', question['params']['message'])
        self.assertIn('Once', question['params']['message'])
        self.assertFalse(self.partner.search_count(created))
        for expected in ('complete', 'input_required'):
            answer = self.call(
                'create_records',
                arguments,
                result['requestState'],
                {'action': 'accept'},
            ).json()['result']
            self.assertEqual(answer['resultType'], expected)
            self.assertEqual(self.partner.search_count(created), 1)

    def test_only_an_acceptance_lets_the_change_through(self):
        for action in ('decline', 'cancel', 'anything'):
            with self.subTest(action):
                state = self.ask()
                result = self.call(
                    'update_records', self.update, state, {'action': action}
                ).json()['result']
                self.assertTrue(result['isError'])
                self.assertEqual(self.partner.name, 'Before')
        for response in (None, {}, 'accept', ['accept'], {'action': None}):
            with self.subTest(response=response):
                self.ask(state=self.ask(), response=response)

    def test_an_answer_counts_for_its_call_only(self):
        accept = {'action': 'accept'}
        other = {**self.update, 'values': {'name': 'Other'}}
        self.ask(other, state=self.ask(), response=accept)
        token, _key = make_mcp_key(self.mcp_user)
        self.ask(state=self.ask(), response=accept, token=token)
        token, _key = make_mcp_key(self.env.ref('base.user_admin'))
        self.ask(state=self.ask(), response=accept, token=token)
        for state in ('unknown', 7, ['unknown']):
            self.ask(state=state, response=accept)
        state = self.ask()
        with patch.object(
            MCPAccessConfirmation, 'MINUTES', PropertyMock(return_value=-1)
        ):
            self.ask(state=state, response=accept)

    def test_a_client_that_cannot_ask_is_refused(self):
        for capabilities in ({}, {'elicitation': {'url': {}}}, {'elicitation': True}):
            with self.subTest(capabilities):
                response = self.call(
                    'update_records', self.update, capabilities=capabilities
                )
                self.assertEqual(response.status_code, 400)
                error = response.json()['error']
                self.assertEqual(error['code'], -32021)
                self.assertIn('elicitation', error['data']['requiredCapabilities'])
        self.assertTrue(self.mcp_tool('update_records', self.update)['isError'])
        self.assertEqual(self.partner.name, 'Before')

    def test_a_caller_cannot_answer_in_the_tool_context(self):
        for answer in ({'answer': 'accept'}, {}, False):
            self.ask({**self.update, 'context': {'mcp_elicitation': answer}})

    def test_every_way_to_change_the_model_asks(self):
        for name, arguments in (
            ('update_records', self.update),
            ('delete_records', {'model': 'res.partner', 'ids': [self.partner.id]}),
            (
                'call_method',
                {
                    'model': 'res.partner',
                    'method': 'write',
                    'ids': [self.partner.id],
                    'args': '[{"name": "After"}]',
                },
            ),
            (
                'post_message',
                {'model': 'res.partner', 'id': self.partner.id, 'body': 'Hi'},
            ),
            (
                'update_records',
                {
                    'model': 'res.partner.category',
                    'ids': self.env['res.partner.category'].create({'name': 'A'}).ids,
                    'values': {
                        'partner_ids': [[1, self.partner.id, {'name': 'After'}]]
                    },
                },
            ),
        ):
            with self.subTest(name, model=arguments['model']):
                result = self.call(name, arguments).json()['result']
                self.assertEqual(result['resultType'], 'input_required')
                self.assertEqual(self.partner.exists().name, 'Before')

    def test_the_question_names_the_records_the_agent_may_see(self):
        for domain, named in ((False, True), ("[('name', '=', 'Else')]", False)):
            self.entry.domain = domain
            with self.subTest(domain):
                result = self.call('update_records', self.update).json()['result']
                message = result['inputRequests']['confirm']['params']['message']
                self.assertEqual('Before' in message, named)

    def test_nothing_else_asks(self):
        read = {'model': 'res.partner', 'ids': [self.partner.id], 'fields': ['name']}
        tag = {'model': 'res.partner.category', 'values': {'name': 'Plain'}}
        for name, arguments in (('read_records', read), ('create_records', tag)):
            with self.subTest(name):
                result = self.call(name, arguments, capabilities={}).json()['result']
                self.assertEqual(result['resultType'], 'complete')
                self.assertFalse(result.get('isError'))
        self.env['muk_mcp.tool']._call('update_records', self.update, self.env)
        self.assertEqual(self.partner.name, 'After')

    def test_a_question_is_logged_as_denied(self):
        self.ask()
        [log] = self.logs([])
        self.assertEqual((log.tool_name, log.status), ('update_records', 'denied'))
