from __future__ import annotations

from odoo import models

from odoo.addons.muk_ai_chatter.tools.mention import mention_plaintext


class DiscussChannel(models.Model):
    """Let an agent be mentioned in a conversation it is not a member of."""

    _inherit = 'discuss.channel'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _ai_answer_mentions(
        self, message: models.BaseModel, agents: models.BaseModel
    ) -> None:
        """Start one session per mentioned agent, owned by the poster, and answer.

        A message a running session posted, or one an agent authored,
        summons nobody, so agents never answer each other.
        """
        if self.env.context.get('muk_mcp_session_id'):
            return
        if message.sudo().author_id._ai_agent_partners():
            return
        prompt = mention_plaintext(message.body)
        if not prompt:
            return
        snapshot = self._ai_thread_context()
        for agent in agents:
            session = self.env['muk_ai.session'].create(
                {
                    'name': self.env._(
                        '%(agent)s on %(record)s',
                        agent=agent.name,
                        record=self.display_name,
                    ),
                    'user_named': True,
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

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def _get_allowed_message_partner_ids(self, partner_ids: list[int]) -> list[int]:
        """Keep the mentioned agents, which are members of no conversation."""
        allowed = set(super()._get_allowed_message_partner_ids(partner_ids))
        allowed |= set(
            self.env['res.partner'].browse(partner_ids)._ai_agent_partners().ids
        )
        return [partner_id for partner_id in partner_ids if partner_id in allowed]
