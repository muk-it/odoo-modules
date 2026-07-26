from __future__ import annotations

from odoo import models
from odoo.tests.common import tagged

from .common import ScheduleTestCommon


@tagged('post_install', '-at_install', 'muk_ai_schedule', 'test_chain')
class TestSessionChain(ScheduleTestCommon):
    """Covers session-chain traversal and the chain navigation action."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _build_chain(self, length: int) -> models.BaseModel:
        """Create a linear chain of ``length`` sessions and return the recordset."""
        chain = self.Session.browse([])
        previous = self.Session.browse([])
        for index in range(length):
            session = self._make_session(
                name=f'Chain Link {index}',
                previous_session_id=previous.id if previous else False,
            )
            chain |= session
            previous = session
        return chain

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_singleton_chain_count_one(self):
        session = self._make_session(name='Lonely')
        self.assertEqual(session.chain_session_count, 1)

    def test_chain_count_walks_both_directions(self):
        chain = self._build_chain(5)
        middle = chain[2]
        self.assertEqual(middle.chain_session_count, 5)

    def test_chain_count_from_head(self):
        chain = self._build_chain(4)
        head = chain[0]
        self.assertEqual(head.chain_session_count, 4)

    def test_chain_count_from_tail(self):
        chain = self._build_chain(4)
        tail = chain[-1]
        self.assertEqual(tail.chain_session_count, 4)

    def test_action_open_chain_returns_full_set(self):
        chain = self._build_chain(3)
        action = chain[1].action_open_chain()
        self.assertEqual(action['res_model'], 'muk_ai.session')
        domain_ids = action['domain'][0][2]
        self.assertEqual(set(domain_ids), set(chain.ids))

    def test_chain_with_branching_descendants(self):
        root = self._make_session(name='Root')
        child_a = self._make_session(name='A', previous_session_id=root.id)
        child_b = self._make_session(name='B', previous_session_id=root.id)
        self.assertEqual(root.chain_session_count, 3)
        self.assertEqual(child_a.chain_session_count, 3)
        self.assertEqual(child_b.chain_session_count, 3)
