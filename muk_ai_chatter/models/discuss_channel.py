from __future__ import annotations

from odoo import _, models

from odoo.addons.muk_ai_chatter.tools import mention_plaintext


class DiscussChannel(models.Model):
    """Let an agent be mentioned in a conversation it is not a member of."""

    _inherit = 'discuss.channel'

    # ----------------------------------------------------------
    # Helper Mention
    # ----------------------------------------------------------

    def _ai_answer_mentions(
        self, message: models.BaseModel, agents: models.BaseModel
    ) -> None:
        """Let the agents mentioned in a conversation answer it."""
        if not self._ai_mention_is_machine_made(message):
            self._ai_spawn_mention_sessions(message, agents)

    def _ai_mention_is_machine_made(self, message: models.BaseModel) -> bool:
        """Return whether a running agent produced this message.

        Two agents mentioning each other would answer each other forever. A
        session posting through a tool writes under its owner's name, so the
        dispatch context is what gives that case away.
        """
        if self.env.context.get('muk_mcp_session_id'):
            return True
        author = message.sudo().author_id
        return bool(author and author._ai_agent_partners())

    def _ai_spawn_mention_sessions(
        self, message: models.BaseModel, agents: models.BaseModel
    ) -> models.BaseModel:
        """Start one session per mentioned agent and let it answer.

        The session belongs to the user who wrote the mention, so every tool it
        runs is bound to what that user is allowed to see.
        """
        sessions = self.env['muk_ai.session']
        prompt = mention_plaintext(message.body)
        if not prompt:
            return sessions
        snapshot = self._ai_thread_context()
        for agent in agents:
            session = sessions.create(
                {
                    'name': _(
                        '%(agent)s on %(record)s',
                        agent=agent.name,
                        record=self.display_name,
                    ),
                    'agent_id': agent.id,
                    'res_model': self._name,
                    'res_id': self.id,
                    'is_mention': True,
                    'mention_message_id': message.id,
                    'mention_context': snapshot,
                }
            )
            session._post_mention_placeholder()
            session.start(prompt)
            sessions |= session
        return sessions

    # ----------------------------------------------------------
    # ORM methods
    # ----------------------------------------------------------

    def _get_allowed_message_partner_ids(self, partner_ids: list[int]) -> list[int]:
        """Keep the mentioned agents among the partners a message may carry.

        The base method admits members of the conversation only, and an agent
        is a member of nothing. Left to that rule the mention would be dropped
        before the thread saw it. Passing it through costs nothing: the agents
        are taken out of the recipients a moment later.
        """
        agents = self.env['res.partner'].browse(partner_ids)._ai_agent_partners()
        allowed = set(super()._get_allowed_message_partner_ids(partner_ids))
        allowed |= set(agents.ids)
        return [partner_id for partner_id in partner_ids if partner_id in allowed]
