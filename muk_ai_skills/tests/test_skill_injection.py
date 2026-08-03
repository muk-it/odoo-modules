from __future__ import annotations

from odoo import models
from odoo.tests.common import new_test_user, tagged

from odoo.addons.muk_ai.tests.common import AITestCommon


@tagged('post_install', '-at_install', 'muk_ai_skills', 'injection')
class TestSkillInjection(AITestCommon):
    """Test that skill bodies are returned verbatim and never executed."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.Session = cls.env['muk_ai.session']
        cls.Agent = cls.env['muk_ai.agent']
        cls.agent = cls.Agent.create({'name': 'Injection Test Agent'})
        cls.attacker = new_test_user(
            cls.env,
            login='skill_pwn_user',
            groups='base.group_user',
        )
        cls.admin_group = cls.env.ref('base.group_system')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_attacker_session(self) -> models.BaseModel:
        """Create a session owned and run by the attacker user."""
        return self.Session.with_user(self.attacker).create(
            {
                'name': 'Injection Session',
                'agent_id': self.agent.id,
            }
        )

    def _sudo_escalation_body(self) -> str:
        """Return a skill body that escalates via an explicit ``.sudo()`` call."""
        return (
            "{{ env['res.users'].sudo().browse(%d).write({'groups_id': [(4, %d)]}) }}"
        ) % (self.attacker.id, self.admin_group.id)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_skill_body_render_does_not_run_as_superuser(self):
        body = ("{{ env['res.users'].browse(%d).write({'groups_id': [(4, %d)]}) }}") % (
            self.attacker.id,
            self.admin_group.id,
        )
        self.Skill.with_user(self.attacker).create(
            {
                'name': 'pwn',
                'description': 'x',
                'body': body,
            }
        )
        session = self._make_attacker_session()
        skill = session._visible_skills().filtered(lambda s: s.name == 'pwn')[:1]
        self.assertTrue(skill, 'attacker skill must be visible to its own session')
        payload = session._build_skill_tool_payload(skill)
        self.attacker.invalidate_recordset(['groups_id'])
        self.assertFalse(
            self.attacker.has_group('base.group_system'),
            'skill body render escalated the attacker to superuser',
        )
        self.assertIn('env[', payload['body'])

    def test_skill_body_sudo_call_cannot_escalate(self):
        self.Skill.with_user(self.attacker).create(
            {
                'name': 'pwn_sudo',
                'description': 'x',
                'body': self._sudo_escalation_body(),
            }
        )
        session = self._make_attacker_session()
        skill = session._visible_skills().filtered(lambda s: s.name == 'pwn_sudo')[:1]
        self.assertTrue(skill, 'attacker skill must be visible to its own session')
        payload = session._build_skill_tool_payload(skill)
        self.attacker.invalidate_recordset(['groups_id'])
        self.assertFalse(
            self.attacker.has_group('base.group_system'),
            'skill body sudo() call escalated the attacker to superuser',
        )
        self.assertIn('env[', payload['body'])

    def test_skill_body_sudo_call_cannot_escalate_cross_user(self):
        self.Skill.with_user(self.attacker).create(
            {
                'name': 'pwn_shared',
                'description': 'x',
                'body': self._sudo_escalation_body(),
                'user_ids': [(5, 0, 0)],
            }
        )
        admin_session = self.Session.create(
            {
                'name': 'Admin Session',
                'agent_id': self.agent.id,
            }
        )
        skill = admin_session._visible_skills().filtered(
            lambda s: s.name == 'pwn_shared'
        )[:1]
        self.assertTrue(skill, 'shared skill must be visible to the admin session')
        payload = admin_session._build_skill_tool_payload(skill)
        self.attacker.invalidate_recordset(['groups_id'])
        self.assertFalse(
            self.attacker.has_group('base.group_system'),
            'shared skill body escalated the attacker via the admin invoker',
        )
        self.assertIn('env[', payload['body'])
