import calendar

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from croniter import croniter

from odoo import _, fields
from odoo.exceptions import ValidationError


WEEKDAY_CODES = {
    'mon': 0,
    'tue': 1,
    'wed': 2,
    'thu': 3,
    'fri': 4,
    'sat': 5,
    'sun': 6,
}

INTERVAL_TYPES = ('minutes', 'hours', 'days', 'weeks', 'months', 'cron')


def _coerce_weekday(weekday):
    if isinstance(weekday, int):
        if 0 <= weekday <= 6:
            return weekday
        raise ValidationError(_(
            "Weekday integer must be between 0 (Mon) and 6 (Sun)."
        ))
    if isinstance(weekday, str):
        code = weekday.lower()
        if code in WEEKDAY_CODES:
            return WEEKDAY_CODES[code]
    raise ValidationError(_(
        "Invalid weekday %(value)s. Expected one of: %(allowed)s.",
        value=weekday,
        allowed=', '.join(WEEKDAY_CODES),
    ))


def compute_next_call(
    interval_type,
    interval_number,
    weekday=None,
    monthday=None,
    cron_expression=None,
    *,
    base=None,
):
    if interval_type not in INTERVAL_TYPES:
        raise ValidationError(_(
            "Invalid interval type %(value)s. Expected one of: %(allowed)s.",
            value=interval_type,
            allowed=', '.join(INTERVAL_TYPES),
        ))

    if base is None:
        base = fields.Datetime.now()
    if not isinstance(base, datetime):
        raise ValidationError(_("Base must be a datetime instance."))

    if interval_type == 'cron':
        if not cron_expression:
            raise ValidationError(_(
                "A cron expression is required when interval_type is 'cron'."
            ))
        try:
            iterator = croniter(cron_expression, base)
        except (ValueError, KeyError) as exc:
            raise ValidationError(_(
                "Invalid cron expression %(value)s: %(error)s",
                value=cron_expression,
                error=exc,
            )) from exc
        return iterator.get_next(datetime)

    if not isinstance(interval_number, int) or interval_number < 1:
        raise ValidationError(_(
            "Interval number must be a positive integer."
        ))

    if interval_type in {'minutes', 'hours', 'days'}:
        return base + timedelta(**{interval_type: interval_number})

    if interval_type == 'weeks':
        if weekday is None:
            raise ValidationError(_(
                "A weekday is required when interval_type is 'weeks'."
            ))
        target_weekday = _coerce_weekday(weekday)
        delta_days = (target_weekday - base.weekday()) % 7 or 7
        result = base + timedelta(days=delta_days)
        if interval_number > 1:
            result = result + timedelta(weeks=interval_number - 1)
        return result

    if interval_type == 'months':
        if not isinstance(monthday, int) or not 1 <= monthday <= 31:
            raise ValidationError(_(
                "A monthday between 1 and 31 is required when interval_type is 'months'."
            ))
        candidate = base.replace(day=1) + relativedelta(months=interval_number)
        time_kw = {
            'hour': base.hour, 'minute': base.minute,
            'second': base.second, 'microsecond': base.microsecond,
        }
        for _attempt in range(12):
            last_day = calendar.monthrange(candidate.year, candidate.month)[1]
            result = candidate.replace(day=min(monthday, last_day), **time_kw)
            if result > base:
                return result
            candidate = candidate + relativedelta(months=1)
        raise ValidationError(_(
            "Could not compute a future month occurrence for monthday %(value)s.",
            value=monthday,
        ))

    raise ValidationError(_(
        "Unhandled interval type %(value)s.",
        value=interval_type,
    ))
