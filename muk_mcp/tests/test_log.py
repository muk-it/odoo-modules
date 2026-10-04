from __future__ import annotations

from unittest.mock import patch

from odoo import fields, models
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import SQL


class TestMcpLog(TransactionCase):
    """Cover the audit log's record shortcuts, retention and visibility."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Keep a handle on the log model."""
        super().setUpClass()
        cls.log_model = cls.env['muk_mcp.log']

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _make_log(self, days_old: int = 0, **values: object) -> models.BaseModel:
        """Create a log row dated ``days_old`` days in the past."""
        log = self.log_model.create({'method': 'tools/call', 'status': 'ok', **values})
        if days_old:
            self.env.cr.execute(
                SQL(
                    'UPDATE %s SET create_date = %s WHERE id = %s',
                    SQL.identifier(log._table),
                    fields.Datetime.subtract(fields.Datetime.now(), days=days_old),
                    log.id,
                ),
            )
            log.invalidate_recordset(['create_date'])
        return log

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_actions_open_the_logged_records(self):
        partner = self.env['res.partner'].create({'name': 'MCP Logged'})
        single = self._make_log(model_name='res.partner', res_id=partner.id)
        self.assertEqual(
            single.action_open_record()['res_id'],
            partner.id,
        )
        missing = self._make_log(model_name='res.partner', res_id=999999999)
        self.assertEqual(missing.action_open_record()['tag'], 'display_notification')
        multi = self._make_log(model_name='res.partner', res_ids=[partner.id])
        self.assertEqual(
            multi.action_open_records()['domain'], [('id', 'in', [partner.id])]
        )
        bare = self._make_log()
        self.assertIsNone(bare.action_open_record())
        self.assertIsNone(bare.action_open_records())
        self.assertEqual(bare.display_name, 'tools/call')
        tool = self._make_log(tool_name='post_message')
        self.assertEqual(tool.display_name, 'tools/call - post_message')

    def test_autovacuum_honours_the_retention(self):
        params = self.env['ir.config_parameter']
        stale = self._make_log(days_old=40)
        fresh = self._make_log(days_old=1)
        with patch.object(self.env.cr, 'commit') as commit:
            params.set_int('muk_mcp.log_autovacuum_days', 90)
            self.log_model._autovacuum_logs()
            self.assertTrue(stale.exists())
            params.set_int('muk_mcp.log_autovacuum_days', 30)
            self.log_model._autovacuum_logs()
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())
        self.assertEqual(commit.call_count, 1)

    def test_users_read_only_their_own_rows(self):
        user = new_test_user(self.env, login='mcp_log_user')
        mine = self._make_log(user_id=user.id)
        theirs = self._make_log(user_id=self.env.ref('base.user_admin').id)
        visible = self.log_model.with_user(user).search(
            [('id', 'in', (mine | theirs).ids)]
        )
        self.assertEqual(visible, mine)
        with self.assertRaises(AccessError):
            theirs.with_user(user).read(['request_data'])
