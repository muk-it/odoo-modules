from unittest.mock import patch

from odoo.addons.muk_ai.models.session import AISession
from odoo.addons.muk_ai.tests.common import ImageCase
from odoo.addons.muk_ai.tools import DEFAULT_CONTEXT_WINDOW


class TestSessionModelSeam(ImageCase):
    """Cover ``AISession._resolve_model_for`` as the session-level override seam."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_the_session_resolves_through_its_agent(self):
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Seam', 'model_id': self.chat_anthropic.id}
        )
        session = self._session(agent)
        self.assertEqual(session._resolve_model_for('chat'), self.chat_anthropic)
        self.assertEqual(session._effective_model(), 'claude-test')
        self.assertEqual(session._resolve_provider(), self.provider_anthropic)
        self.assertEqual(session._resolve_context_window(), 200000)

    def test_an_override_of_the_seam_moves_model_provider_and_window(self):
        other = self._create_model('seam-override', context_window=900000)
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Seam', 'model_id': self.chat_anthropic.id}
        )
        session = self._session(agent)
        with patch.object(
            AISession,
            '_resolve_model_for',
            lambda record, modality: (
                other if modality == 'chat' else record.env['muk_ai.model']
            ),
        ):
            self.assertEqual(session._effective_model(), 'seam-override')
            self.assertEqual(session._resolve_provider(), self.provider)
            self.assertEqual(session._resolve_context_window(), 900000)
        self.assertEqual(session._effective_model(), 'claude-test')
        self.assertEqual(session._resolve_context_window(), 200000)

    def test_the_seam_carries_the_image_modality(self):
        agent = self.env['muk_ai.agent'].create(
            {'name': 'Seam', 'enable_image_generation': True}
        )
        session = self._session(agent)
        tool = self.env['muk_mcp.mixin'].with_context(muk_mcp_session_id=session.id)
        with patch.object(
            AISession,
            '_resolve_model_for',
            lambda record, modality: self.image,
        ):
            self.assertEqual(tool._image_model(), self.image)

    def test_the_context_window_falls_back_to_the_provider_default(self):
        default_model = self._create_model('seam-default', context_window=64000)
        self.provider.default_chat_model_id = default_model
        agent = self.env['muk_ai.agent'].create({'name': 'Seam'})
        self.assertEqual(self._session(agent)._resolve_context_window(), 64000)

    def test_the_context_window_falls_back_to_the_hard_default(self):
        self._clear_default_models()
        agent = self.env['muk_ai.agent'].create({'name': 'Seam'})
        session = self._session(agent)
        self.assertFalse(session._effective_model())
        self.assertEqual(session._resolve_context_window(), DEFAULT_CONTEXT_WINDOW)
