from __future__ import annotations

from odoo.tests import HttpCase, tagged

from .common import SubagentTestCommon, delegate_payload, text_payload


@tagged('post_install', '-at_install')
class TestSubagentTour(HttpCase, SubagentTestCommon):
    """Walk a finished delegation through the real chat client."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Seed one finished run, owned by the user the tours log in as.

        Seeded for the class rather than inside a test: the browser reads
        the database as the class left it. A chat also belongs to whoever
        started it, and both the sidebar and the session list say so, so a
        run seeded as anyone else is simply not on the page.
        """
        super().setUpClass()
        env = cls.env(user=cls.env.ref('base.user_admin'))
        worker = cls.worker.with_env(env).copy({'name': 'Tour worker'})
        lead = cls.lead.with_env(env).copy(
            {'name': 'Tour lead', 'delegate_agent_ids': [(6, 0, worker.ids)]}
        )
        cls.lead_chat = env['muk_ai.session'].create(
            {'name': 'Tour lead', 'agent_id': lead.id}
        )
        payloads = [
            delegate_payload(
                [{'agent': 'Tour worker', 'objective': 'Count the sale orders'}]
            ),
            text_payload('Counted 40 orders in the quarter.'),
            text_payload('Forty orders were placed this quarter.'),
        ]
        with SubagentTestCommon._mock_responses(cls, payloads):
            cls.lead_chat.start('How many orders this quarter?')
        # A chat names itself after its first message, so the name given at
        # creation is gone by now; the tour looks for this one.
        cls.lead_chat.name = 'Tour lead'
        cls.worker_chat = cls.lead_chat.child_session_ids

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_finished_run_is_walkable_from_the_strip_to_the_subagent(self):
        # The sidebar lists what no space collects, so a run hidden there
        # would fail the tour for a reason that is not the browser's.
        general = self.env['muk_ai.space'].fetch_general_domain()
        listed = self.env['muk_ai.session'].search(general)
        self.assertIn(self.lead_chat, listed)
        self.assertNotIn(self.worker_chat, listed)
        self.start_tour('/odoo/ai', 'muk_ai_subagents_run_tour', login='admin')

    def test_a_subagent_is_an_ordinary_session_in_the_backend(self):
        self.assertEqual(self.worker_chat.parent_session_id, self.lead_chat)
        self.assertEqual(self.worker_chat.stop_reason, 'done')
        self.start_tour(
            '/odoo/ai-sessions', 'muk_ai_subagents_backend_tour', login='admin'
        )
