from __future__ import annotations

import json

from odoo import models
from odoo.tests.common import tagged

from .common import SubagentTestCommon


@tagged('post_install', '-at_install', 'muk_ai_subagents')
class TestLoop(SubagentTestCommon):
    """Verify the repeated-call ladder: notice, withhold, stop."""

    def _child(self) -> tuple[models.Model, models.Model]:
        """Return a parent and a subagent created for it without starting it."""
        parent = self._session()
        child = self.Session.with_context(muk_ai_subagent_spawn=True).create(
            {
                'name': 'subagent',
                'agent_id': self.worker.id,
                'parent_session_id': parent.id,
                'delegation_brief': {
                    'objective': 'x',
                    'color': 'red',
                    'call_id': 'd1',
                },
            }
        )
        return parent, child

    def _repeat(self, child: models.Model, outputs: list, result: str = '[]') -> None:
        """Track one more identical search_read call on ``child``."""
        child._track_tool_fingerprint(
            outputs, 'search_read', {'model': 'res.partner'}, result
        )

    def _call(self, index: int) -> dict:
        """Build the provider round that searches partners and narrates it."""
        return self._tool_payload(
            'search_read',
            {'model': 'res.partner'},
            f's{index}',
            text=f'partial {index}',
        )

    def test_ladder_notice_withhold_halt(self):
        _parent, child = self._child()
        outputs = []
        self._repeat(child, outputs)
        self._repeat(child, outputs)
        self.assertEqual(outputs, [])
        self._repeat(child, outputs)
        self.assertEqual(len(outputs), 1)
        self.assertIn('<loop_notice>', outputs[0]['content'][0]['text'])
        self.assertFalse(child._withheld_tool_names())
        self._repeat(child, outputs)
        self.assertEqual(child._withheld_tool_names(), {'search_read'})
        self.assertNotIn('search_read', {e['name'] for e in child._get_tool_schema()})
        self.assertFalse(child.loop_state.get('halt'))
        child._tick_round()
        self.assertEqual(child._withheld_tool_names(), {'search_read'})
        child._tick_round()
        self.assertFalse(child._withheld_tool_names())
        self.assertIn('search_read', {e['name'] for e in child._get_tool_schema()})
        self._repeat(child, outputs)
        self.assertTrue(child.loop_state['halt'])

    def test_varying_results_are_not_a_loop(self):
        _parent, child = self._child()
        outputs = []
        for index in range(4):
            self._repeat(child, outputs, result=f'[{index}]')
        self.assertEqual(outputs, [])
        self.assertFalse(child._withheld_tool_names())

    def test_withheld_call_is_refused(self):
        _parent, child = self._child()
        child.loop_state = {'withheld': {'search_read': 2}}
        call = {'name': 'search_read', 'arguments': {}, 'call_id': 'x1'}
        outputs = []
        self.assertFalse(child._execute_tool_call(call, [call], outputs, 0, False))
        self.assertIn('tool_withheld', json.loads(outputs[0]['output'])['error'])

    def test_no_progress_stops_child_and_keeps_partial_results(self):
        parent, child = self._child()
        tool_patch, calls = self._patch_tool({'search_read': '[]'})
        rounds = [self._call(index) for index in range(1, 7)]
        with tool_patch, self._mock_responses(rounds):
            child.start('go')
        self.assertEqual(child.state, 'error')
        self.assertEqual(child.stop_reason, 'no_progress')
        self.assertEqual(child.last_text, 'partial 6')
        self.assertEqual(calls.count('search_read'), 5)
        refused = [
            json.loads(item['output'])
            for item in child.conversation
            if item.get('type') == 'function_call_output' and item['call_id'] == 's5'
        ]
        self.assertIn('tool_withheld', refused[0]['error'])
        result = self._events(parent, 'delegation_result')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.payload['stop_reason'], 'no_progress')
        self.assertEqual(result.payload['summary'], 'partial 6')

    def test_loop_state_persists_across_turns(self):
        _parent, child = self._child()
        outputs = []
        for _ in range(3):
            self._repeat(child, outputs)
        child.invalidate_recordset()
        self.assertEqual(len(child.loop_state['recent']), 3)
        self.assertEqual(list(child.loop_state['strikes'].values()), [1])
