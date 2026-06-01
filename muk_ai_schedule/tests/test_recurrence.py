from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.muk_ai_schedule.tools.recurrence import compute_next_call


@tagged('post_install', '-at_install', 'muk_ai_schedule')
class TestRecurrence(TransactionCase):

    def test_minutes_interval(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        result = compute_next_call('minutes', 15, base=base)
        self.assertEqual(result, datetime(2026, 1, 1, 12, 15, 0))

    def test_hours_interval(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        result = compute_next_call('hours', 3, base=base)
        self.assertEqual(result, datetime(2026, 1, 1, 15, 0, 0))

    def test_days_interval(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        result = compute_next_call('days', 7, base=base)
        self.assertEqual(result, datetime(2026, 1, 8, 12, 0, 0))

    def test_weeks_next_weekday(self):
        base = datetime(2026, 1, 5, 9, 0, 0)
        result = compute_next_call('weeks', 1, weekday='wed', base=base)
        self.assertEqual(result, datetime(2026, 1, 7, 9, 0, 0))

    def test_weeks_skip_two_weeks(self):
        base = datetime(2026, 1, 5, 9, 0, 0)
        result = compute_next_call('weeks', 2, weekday='wed', base=base)
        self.assertEqual(result, datetime(2026, 1, 14, 9, 0, 0))

    def test_weeks_same_weekday_jumps_to_next_week(self):
        base = datetime(2026, 1, 5, 9, 0, 0)
        result = compute_next_call('weeks', 1, weekday='mon', base=base)
        self.assertEqual(result, datetime(2026, 1, 12, 9, 0, 0))

    def test_months_basic(self):
        base = datetime(2026, 1, 15, 10, 30, 0)
        result = compute_next_call('months', 1, monthday=15, base=base)
        self.assertEqual(result, datetime(2026, 2, 15, 10, 30, 0))

    def test_months_overflow_to_last_day(self):
        base = datetime(2026, 1, 31, 8, 0, 0)
        result = compute_next_call('months', 1, monthday=31, base=base)
        self.assertEqual(result, datetime(2026, 2, 28, 8, 0, 0))

    def test_months_skip_two_months(self):
        base = datetime(2026, 1, 10, 0, 0, 0)
        result = compute_next_call('months', 2, monthday=10, base=base)
        self.assertEqual(result, datetime(2026, 3, 10, 0, 0, 0))

    def test_cron_next_monday_9am(self):
        base = datetime(2026, 1, 1, 0, 0, 0)
        result = compute_next_call('cron', 1, cron_expression='0 9 * * 1', base=base)
        self.assertEqual(result, datetime(2026, 1, 5, 9, 0, 0))

    def test_invalid_interval_type(self):
        with self.assertRaises(ValidationError):
            compute_next_call('decades', 1, base=datetime(2026, 1, 1))

    def test_cron_bad_expression(self):
        with self.assertRaises(ValidationError):
            compute_next_call(
                'cron', 1,
                cron_expression='not a cron',
                base=datetime(2026, 1, 1),
            )

    def test_cron_missing_expression(self):
        with self.assertRaises(ValidationError):
            compute_next_call('cron', 1, base=datetime(2026, 1, 1))

    def test_weeks_missing_weekday(self):
        with self.assertRaises(ValidationError):
            compute_next_call('weeks', 1, base=datetime(2026, 1, 1))

    def test_months_invalid_monthday(self):
        with self.assertRaises(ValidationError):
            compute_next_call('months', 1, monthday=32, base=datetime(2026, 1, 1))

    def test_negative_interval_number(self):
        with self.assertRaises(ValidationError):
            compute_next_call('minutes', 0, base=datetime(2026, 1, 1))
