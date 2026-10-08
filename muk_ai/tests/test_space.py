from __future__ import annotations

from odoo import models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload


class TestSpace(AITestCommon):
    """Verify how personal and system spaces collect, hold and instruct chats."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create two users."""
        super().setUpClass()
        cls.member = new_test_user(cls.env, login='space_member')
        cls.other = new_test_user(cls.env, login='space_other')

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _space(self, name: str, **values) -> models.BaseModel:
        """Create a space, personal to the current user unless told otherwise."""
        return self.env['muk_ai.space'].create({'name': name, **values})

    def _system(
        self, name: str, domain: str = "[('id', '>', 0)]", **values
    ) -> models.BaseModel:
        """Create a system space collecting its chats through ``domain``."""
        return self._space(name, user_id=False, domain=domain, **values)

    def _listed(self, user: models.BaseModel) -> set[int]:
        """Return the ids of the spaces the sidebar shows ``user``."""
        rows = self.env['muk_ai.space'].with_user(user).fetch_spaces()
        return {row['id'] for row in rows}

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_a_space_refuses_what_it_cannot_hold(self):
        mine = self._space('Mine', instructions='Answer in German.')
        theirs = self._space('Theirs', user_id=self.other.id)
        system = self._system('Scheduled')
        pinned = self._system('Pinned', pinned=True)
        owned = self._space('Owned', user_id=self.member.id).with_user(self.member)
        system_domain = "[('id', '>', 0)]"
        for label, attempt in (
            ('file into a system space', lambda: self._session(space_id=system.id)),
            ('file into a foreign space', lambda: self._session(space_id=theirs.id)),
            ('malformed domain', lambda: self._system('Broken', 'not a domain')),
            ('non-list domain', lambda: self._system('Broken', "{'a': 1}")),
            ('unknown field', lambda: self._system('Broken', "[('nope', '=', 1)]")),
            ('no owner, no domain', lambda: self._space('Nowhere', user_id=False)),
            ('pin a personal space', lambda: self._space('Pin', pinned=True)),
            (
                'unpin by dropping the domain',
                lambda: pinned.write({'user_id': self.env.uid, 'domain': False}),
            ),
            (
                'instructions on a new system space',
                lambda: self._system('Told', instructions='Answer in German.'),
            ),
            (
                'instructions on a system space',
                lambda: system.write({'instructions': 'Answer in German.'}),
            ),
            (
                'instructions carried into a system space',
                lambda: mine.write({'user_id': False, 'domain': system_domain}),
            ),
            (
                'forge a system space',
                lambda: owned.write({'user_id': False, 'domain': "[(1, '=', 1)]"}),
            ),
            ('hand a space away', lambda: owned.write({'user_id': self.other.id})),
        ):
            with self.subTest(label), self.assertRaises(ValidationError):
                attempt()

    def test_a_space_lets_go_of_the_chats_it_can_no_longer_hold(self):
        for label, change, released in (
            ('renamed', lambda space, chat: space.write({'name': 'Renamed'}), False),
            (
                'chat handed over',
                lambda space, chat: chat.action_handover(self.other.id),
                True,
            ),
            (
                'space given away',
                lambda space, chat: space.write({'user_id': self.other.id}),
                True,
            ),
            (
                'space turned system',
                lambda space, chat: space.write(
                    {'user_id': False, 'domain': "[('id', '>', 0)]"}
                ),
                True,
            ),
            ('space deleted', lambda space, chat: space.unlink(), True),
        ):
            with self.subTest(label):
                space = self._space('Q3 Budget')
                session = self._session(space_id=space.id)
                change(space, session)
                self.assertTrue(session.exists())
                self.assertEqual(not session.space_id, released)

    def test_the_sidebar_lists_own_and_system_spaces(self):
        mine = self._space('Mine', user_id=self.member.id)
        theirs = self._space('Theirs', user_id=self.other.id)
        system = self._system('Shared')
        spaces = {mine.id, theirs.id, system.id}
        for user, visible in (
            (self.member, {mine.id, system.id}),
            (self.other, {theirs.id, system.id}),
            (self.env.user, {system.id}),
        ):
            with self.subTest(user=user.login):
                self.assertEqual(self._listed(user) & spaces, visible)

    def test_only_a_system_user_shapes_a_system_space(self):
        system = self._system('Shared')
        mine = self._space('Mine', user_id=self.member.id).with_user(self.member)
        with self.assertRaises(AccessError):
            system.with_user(self.member).write({'name': 'Hijacked'})
        with self.assertRaises(UserError):
            system.unlink()
        self.assertEqual([system.can_edit_domain, mine.can_edit_domain], [True, False])
        mine.write({'name': 'Renamed', 'instructions': 'Answer in German.'})
        self.assertEqual(mine.name, 'Renamed')
        mine.unlink()
        self.assertFalse(mine.exists())
        self.assertTrue(system.exists())

    def test_fetch_spaces_describes_each_space(self):
        agent = self.env['muk_ai.agent'].create({'name': 'Space Agent'})
        mine = self._space(
            'Q3 Budget', agent_id=agent.id, instructions='Answer in German.'
        )
        system = self._system('Everything', pinned=True)
        filed = self._session(space_id=mine.id)
        loose = self._session()
        entries = {row['id']: row for row in self.env['muk_ai.space'].fetch_spaces()}
        for space, expected, collected, left in (
            (
                mine,
                {
                    'name': 'Q3 Budget',
                    'agent_id': agent.id,
                    'agent_name': 'Space Agent',
                    'instructions': 'Answer in German.',
                    'system': False,
                    'pinned': False,
                },
                filed,
                loose,
            ),
            (
                system,
                {
                    'name': 'Everything',
                    'agent_id': False,
                    'agent_name': '',
                    'instructions': '',
                    'system': True,
                    'pinned': True,
                },
                loose,
                filed,
            ),
        ):
            with self.subTest(space=space.name):
                entry = entries[space.id]
                self.assertEqual({key: entry[key] for key in expected}, expected)
                found = self.env['muk_ai.session'].search(entry['session_domain'])
                self.assertIn(collected, found)
                self.assertNotIn(left, found)

    def test_count_sessions_sorts_chats_into_the_visible_spaces(self):
        first = self._space('First')
        second = self._space('Second')
        theirs = self._space('Theirs', user_id=self.other.id)
        system = self._system('By name', "[('name', '=', 'Collected')]")
        one = self._session(space_id=first.id)
        two = self._session(space_id=first.id)
        filed = self._session(name='Collected', space_id=second.id)
        loose = self._session(name='Collected')
        foreign = (
            self.env['muk_ai.session']
            .with_user(self.other)
            .create({'name': 'Foreign', 'space_id': theirs.id})
        )
        spaces = {str(space.id) for space in first | second | theirs | system}
        for ids, expected in (
            (
                [one.id, two.id, filed.id, loose.id],
                {first: 2, second: 1, system: 1},
            ),
            ([two.id], {first: 1}),
            ([foreign.id], {}),
            ([], {}),
        ):
            with self.subTest(ids=ids):
                counts = self.env['muk_ai.space'].count_sessions(ids)
                self.assertEqual(
                    {key: count for key, count in counts.items() if key in spaces},
                    {str(space.id): count for space, count in expected.items()},
                )

    def test_counting_personal_spaces_shares_one_query(self):
        spaces = self._system('By name', "[('name', '=', 'Counted')]")
        spaces |= self._system('By id', "[('id', '<', 0)]")
        for index in range(5):
            space = self._space(f'Space {index}')
            self._session(name='Counted', space_id=space.id)
            spaces |= space
        self._session(name='Counted')
        spaces.invalidate_recordset(['session_count'])
        with self.assertQueryCount(3):
            counts = spaces.mapped('session_count')
        self.assertEqual(counts, [1, 0, 1, 1, 1, 1, 1])

    def test_the_space_instructions_reach_the_system_prompt(self):
        raw = 'Secret: {{ env["ir.config_parameter"].sudo().get_str("database.uuid") }}'
        for label, instructions, filed, unfiled, expected in (
            ('filed', 'Answer in German.', True, False, 'Answer in German.'),
            ('handed over as written', raw, True, False, raw),
            ('loose chat', 'Answer in German.', False, False, None),
            ('blank instructions', '   \n  ', True, False, None),
            ('taken out again', 'Answer in German.', True, True, None),
        ):
            with self.subTest(label):
                space = self._space('Q3 Budget', instructions=instructions)
                session = self._session(space_id=filed and space.id)
                if unfiled:
                    session.space_id = False
                with self._mock_responses([text_payload()]) as requests:
                    session.send_message('hello')
                system = self._system_prompt(requests[0])
                if expected is None:
                    self.assertNotIn('<space_instructions>', system)
                    continue
                start = system.index('<space_instructions>')
                block = system[start : system.index('\n<runtime>\n')]
                self.assertIn('Q3 Budget', block)
                self.assertIn(expected, block)

    def test_filing_an_unread_chat_pushes_the_badge(self):
        space = self._space('Q3 Budget')
        for unread, badges in ((True, [1]), (False, [])):
            with self.subTest(unread=unread):
                session = self._session(notification_unread=unread)
                with self._capture_bus() as sent:
                    session.space_id = space
                self.assertEqual(
                    [
                        message['space_unread'].get(str(space.id))
                        for _target, kind, message in sent
                        if kind == 'muk_ai.notification_badge'
                    ],
                    badges,
                )

    def test_reorder_stores_the_given_order(self):
        first, second, third = (self._space(name) for name in ('A', 'B', 'C'))
        self.env['muk_ai.space'].reorder([third.id, first.id, second.id])
        ordered = self.env['muk_ai.space'].search(
            [('id', 'in', [first.id, second.id, third.id])]
        )
        self.assertEqual(ordered.ids, [third.id, first.id, second.id])
