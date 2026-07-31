from __future__ import annotations

from unittest.mock import patch

from odoo import models
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import new_test_user

from odoo.addons.muk_ai.models.session import AISession
from odoo.addons.muk_ai.tests.common import AITestCommon


class TestSpace(AITestCommon):
    """Verify how personal and system spaces collect their chats."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _space(self, name: str, **values) -> models.Model:
        """Create a space owned by the current user unless told otherwise."""
        return self.env['muk_ai.space'].create({'name': name, **values})

    def _session(self, name: str, **values) -> models.Model:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': name, **values})

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_personal_space_defaults_to_the_current_user(self):
        space = self._space('Q3 Budget')
        self.assertEqual(space.user_id, self.env.user)
        self.assertFalse(space.domain)

    def test_filing_a_chat_into_an_own_space(self):
        space = self._space('Q3 Budget')
        session = self._session('Filed', space_id=space.id)
        self.assertEqual(session.space_id, space)
        self.assertEqual(space.session_count, 1)

    def test_filing_into_a_system_space_is_refused(self):
        space = self._space('Scheduled', user_id=False, domain="[('id', '>', 0)]")
        with self.assertRaises(ValidationError):
            self._session('Nope', space_id=space.id)

    def test_filing_into_another_users_space_is_refused(self):
        other = new_test_user(self.env, login='space_other')
        space = self._space('Theirs', user_id=other.id)
        with self.assertRaises(ValidationError):
            self._session('Nope', space_id=space.id)

    def test_a_system_space_collects_matching_chats(self):
        session = self._session('Derived')
        space = self._space(
            'By Name',
            user_id=False,
            domain=f"[('id', '=', {session.id})]",
        )
        self.assertEqual(space.session_count, 1)

    def test_a_filed_chat_leaves_its_system_space(self):
        session = self._session('Derived')
        system = self._space(
            'By Name',
            user_id=False,
            domain=f"[('id', '=', {session.id})]",
        )
        personal = self._space('Q3 Budget')
        session.space_id = personal
        self.assertEqual(system.session_count, 0)
        self.assertEqual(personal.session_count, 1)

    def test_fetch_spaces_describes_a_personal_space(self):
        space = self._space('Q3 Budget')
        entry = next(
            row
            for row in self.env['muk_ai.space'].fetch_spaces()
            if row['id'] == space.id
        )
        self.assertFalse(entry['system'])
        self.assertEqual(entry['session_domain'], [('space_id', '=', space.id)])

    def test_count_sessions_sorts_ids_into_personal_spaces(self):
        space = self._space('Q3 Budget')
        other = self._space('Website')
        first = self._session('One', space_id=space.id)
        second = self._session('Two', space_id=space.id)
        third = self._session('Three', space_id=other.id)
        counts = self.env['muk_ai.space'].count_sessions(
            [first.id, second.id, third.id]
        )
        self.assertEqual(counts[str(space.id)], 2)
        self.assertEqual(counts[str(other.id)], 1)

    def test_count_sessions_sorts_ids_into_system_spaces(self):
        session = self._session('Derived')
        space = self._space(
            'By Id',
            user_id=False,
            domain=f"[('id', '=', {session.id})]",
        )
        counts = self.env['muk_ai.space'].count_sessions([session.id])
        self.assertEqual(counts[str(space.id)], 1)

    def test_count_sessions_ignores_sessions_outside_the_given_ids(self):
        space = self._space('Q3 Budget')
        self._session('Counted', space_id=space.id)
        skipped = self._session('Skipped', space_id=space.id)
        counts = self.env['muk_ai.space'].count_sessions([skipped.id])
        self.assertEqual(counts[str(space.id)], 1)

    def test_counting_personal_spaces_does_not_query_per_space(self):
        spaces = self.env['muk_ai.space']
        for index in range(5):
            space = self._space(f'Space {index}')
            self._session(f'Chat {index}', space_id=space.id)
            spaces |= space
        spaces.invalidate_recordset(['session_count'])
        with patch.object(AISession, 'search_count', autospec=True) as counted:
            self.assertEqual(sum(spaces.mapped('session_count')), 5)
        self.assertFalse(
            counted.called,
            'personal spaces must share one grouped query, not one each',
        )

    def test_counting_system_spaces_costs_one_query_each(self):
        session = self._session('Derived')
        first = self._space(
            'By Id', user_id=False, domain=f"[('id', '=', {session.id})]"
        )
        second = self._space(
            'By Name', user_id=False, domain="[('name', '=', 'Derived')]"
        )
        spaces = first | second
        spaces.invalidate_recordset(['session_count'])
        with patch.object(
            AISession, 'search_count', autospec=True, return_value=1
        ) as counted:
            spaces.mapped('session_count')
        self.assertEqual(counted.call_count, 2)

    def test_count_sessions_without_ids_is_empty(self):
        space = self._space('Q3 Budget')
        self._session('One', space_id=space.id)
        self.assertEqual(self.env['muk_ai.space'].count_sessions([]), {})

    def test_the_badge_payload_carries_the_per_space_counts(self):
        space = self._space('Q3 Budget')
        self._session('Unread', space_id=space.id, notification_unread=True)
        self._session('Read', space_id=space.id, notification_unread=False)
        payload = self.env['muk_ai.session'].notification_badge()
        self.assertEqual(payload['space_unread'][str(space.id)], 1)

    def test_fetch_spaces_omits_unread_so_only_the_badge_reports_it(self):
        space = self._space('Q3 Budget')
        entry = next(
            row
            for row in self.env['muk_ai.space'].fetch_spaces()
            if row['id'] == space.id
        )
        self.assertNotIn('unread', entry)

    def test_fetch_spaces_marks_a_system_space(self):
        space = self._space('Scheduled', user_id=False, domain="[('id', '>', 0)]")
        entry = next(
            row
            for row in self.env['muk_ai.space'].fetch_spaces()
            if row['id'] == space.id
        )
        self.assertTrue(entry['system'])
        self.assertIn(('space_id', '=', False), entry['session_domain'])

    def test_handing_over_a_filed_chat_releases_it(self):
        other = new_test_user(self.env, login='space_handover')
        space = self._space('Q3 Budget')
        session = self._session('Filed', space_id=space.id)
        session.action_handover(other.id)
        self.assertEqual(session.sudo().user_id, other)
        self.assertFalse(session.sudo().space_id)

    def test_a_user_cannot_turn_their_space_into_a_system_space(self):
        member = new_test_user(self.env, login='space_forger')
        space = self._space('Mine', user_id=member.id)
        with self.assertRaises(ValidationError):
            space.with_user(member).write({'user_id': False, 'domain': "[(1, '=', 1)]"})

    def test_a_user_cannot_hand_their_space_to_someone_else(self):
        member = new_test_user(self.env, login='space_giver')
        victim = new_test_user(self.env, login='space_victim')
        space = self._space('Mine', user_id=member.id)
        with self.assertRaises(ValidationError):
            space.with_user(member).write({'user_id': victim.id})

    def test_fetch_spaces_hides_other_users_spaces_from_an_admin(self):
        other = new_test_user(self.env, login='space_stranger')
        theirs = self._space('Theirs', user_id=other.id)
        mine = self._space('Mine')
        listed = {row['id'] for row in self.env['muk_ai.space'].fetch_spaces()}
        self.assertIn(mine.id, listed)
        self.assertNotIn(theirs.id, listed)

    def test_a_domain_naming_an_unknown_field_is_refused(self):
        with self.assertRaises(ValidationError):
            self._space('Broken', user_id=False, domain="[('nope_no_field', '=', 1)]")

    def test_reorder_stores_the_given_order(self):
        first = self._space('First')
        second = self._space('Second')
        third = self._space('Third')
        self.env['muk_ai.space'].reorder([third.id, first.id, second.id])
        ordered = self.env['muk_ai.space'].search(
            [('id', 'in', [first.id, second.id, third.id])]
        )
        self.assertEqual(list(ordered), [third, first, second])

    def test_fetch_spaces_carries_the_icon(self):
        space = self._space('Q3 Budget')
        entry = next(
            row
            for row in self.env['muk_ai.space'].fetch_spaces()
            if row['id'] == space.id
        )
        self.assertEqual(entry['icon'], 'fa-folder-o')

    def test_giving_a_space_away_releases_the_chats_of_its_owner(self):
        other = new_test_user(self.env, login='space_receiver')
        space = self._space('Q3 Budget')
        session = self._session('Filed', space_id=space.id)
        space.user_id = other
        self.assertFalse(session.space_id)

    def test_turning_a_space_into_a_system_one_releases_its_chats(self):
        space = self._space('Q3 Budget')
        session = self._session('Filed', space_id=space.id)
        space.write({'user_id': False, 'domain': "[('id', '>', 0)]"})
        self.assertFalse(session.space_id)

    def test_filing_an_unread_chat_pushes_the_badge(self):
        space = self._space('Q3 Budget')
        session = self._session('Unread', notification_unread=True)
        captured = []

        def fake(self_arg, target, notification_type, message):
            captured.append(notification_type)

        with patch.object(
            type(self.env['bus.bus']), '_sendone', autospec=True, side_effect=fake
        ):
            session.space_id = space
        self.assertIn('muk_ai.notification_badge', captured)

    def test_a_malformed_domain_is_refused(self):
        with self.assertRaises(ValidationError):
            self._space('Broken', user_id=False, domain='not a domain')

    def test_a_non_list_domain_is_refused(self):
        with self.assertRaises(ValidationError):
            self._space('Broken', user_id=False, domain="{'a': 1}")

    def test_a_user_only_sees_their_own_and_the_system_spaces(self):
        other = new_test_user(self.env, login='space_reader')
        mine = self._space('Mine')
        theirs = self._space('Theirs', user_id=other.id)
        system = self._space('Shared', user_id=False, domain="[('id', '>', 0)]")
        visible = self.env['muk_ai.space'].with_user(other).search([])
        self.assertIn(theirs, visible)
        self.assertIn(system, visible)
        self.assertNotIn(mine, visible)

    def test_a_user_cannot_edit_a_system_space(self):
        space = self._space('Shared', user_id=False, domain="[('id', '>', 0)]")
        reader = new_test_user(self.env, login='space_editor')
        with self.assertRaises(AccessError):
            space.with_user(reader).write({'name': 'Hijacked'})

    def test_deleting_a_space_keeps_its_chats(self):
        space = self._space('Q3 Budget')
        session = self._session('Filed', space_id=space.id)
        space.unlink()
        self.assertTrue(session.exists())
        self.assertFalse(session.space_id)

    def test_a_space_without_owner_and_domain_is_refused(self):
        with self.assertRaises(ValidationError):
            self._space('Nowhere', user_id=False)

    def test_opening_a_space_lists_the_chats_it_collects(self):
        space = self._space('Q3 Budget')
        filed = self._session('Filed', space_id=space.id)
        loose = self._session('Loose')
        action = space.action_open_sessions()
        listed = self.env['muk_ai.session'].search(action['domain'])
        self.assertEqual(action['res_model'], 'muk_ai.session')
        self.assertIn(filed, listed)
        self.assertNotIn(loose, listed)

    def test_opening_a_system_space_drops_the_filter_of_its_menu(self):
        space = self._space('Shared', user_id=False, domain="[('id', '>', 0)]")
        action = space.action_open_sessions()
        self.assertFalse(action['context'])
