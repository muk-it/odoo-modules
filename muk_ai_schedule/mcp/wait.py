from __future__ import annotations

from datetime import datetime, timedelta, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.muk_ai_schedule.tools.constants import (
    DEFAULT_MAX_WAITS,
    MAX_DELAY_SECONDS,
    MAX_NOTE_CHARS,
    MIN_DELAY_SECONDS,
    WAIT_TOOL,
)
from odoo.addons.muk_mcp.core.tool import mcp_tool


class AIWaitTools(models.AbstractModel):
    """Expose the MCP tool a chat uses to pause itself until it is woken."""

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _check_can_wait(self) -> None:
        """Check that the current AI session may pause itself now.

        :raise UserError: when called outside a session, through ``tool_load``,
            or once the chat has waited as often as it may
        """
        session = self._resolve_mcp_session(
            self.env._('The wait tool can only be called inside an AI chat.')
        )
        if not self.env.context.get('muk_ai_wait_call_id'):
            raise UserError(
                self.env._(
                    'Call wait directly from your tools array, never through tool_load.'
                )
            )
        limit = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('muk_ai_schedule.max_waits', DEFAULT_MAX_WAITS)
        )
        if session.wake_count >= limit:
            raise UserError(
                self.env._(
                    'This chat may wait %s times and has used them all. Finish the task now.',
                    limit,
                )
            )

    def _wait_until(self, seconds: int | None, until: str | None) -> datetime:
        """Return the moment a wait ends, given in seconds or as an ISO 8601 time.

        :raise UserError: when neither or both are given, or the delay is out of bounds
        """
        if (seconds is None) == (until is None):
            raise UserError(self.env._("Give exactly one of 'seconds' or 'until'."))
        now = fields.Datetime.now()
        if seconds is not None:
            moment = now + timedelta(seconds=int(seconds))
        else:
            try:
                moment = datetime.fromisoformat(until)
            except ValueError:
                raise UserError(
                    self.env._("'until' must be an ISO 8601 time, not %r.", until)
                ) from None
            if moment.tzinfo:
                moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
        if not MIN_DELAY_SECONDS <= (moment - now).total_seconds() <= MAX_DELAY_SECONDS:
            raise UserError(
                self.env._(
                    'A wait lasts between %(min)s seconds and %(max)s days.',
                    min=MIN_DELAY_SECONDS,
                    max=MAX_DELAY_SECONDS // 86400,
                )
            )
        return moment.replace(microsecond=0)

    def _wait_record(self, model: str, record_id: int) -> models.Model:
        """Return the record a wait watches.

        :raise UserError: when the model is unknown or the record is not there
        """
        if model not in self.env:
            raise UserError(self.env._('Unknown model %s.', model))
        record = self.env[model].browse(int(record_id)).exists()
        if not record:
            raise UserError(
                self.env._(
                    '%(model)s %(id)s does not exist.', model=model, id=record_id
                )
            )
        record.check_access('read')
        return record

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name=WAIT_TOOL,
        description=(
            'Pause this chat and carry on later, without anybody watching. Use '
            'it to wait for a time, for a record to reach a state, or for a '
            'reply posted on a record. Give exactly one of "seconds" or '
            '"until": the moment you wake up, or, when you watch a record, '
            'the longest you wait for it. To watch a record give "model" and '
            '"record_id" with a "condition" (a domain on that record, checked '
            'every minute) and/or "on_message" (wake when a message is posted '
            'on it). The result tells why and when (UTC) you woke up and repeats your note; '
            'a condition that already holds returns at once. To keep checking '
            'on a cadence, call wait again after each check.'
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'note': {
                    'type': 'string',
                    'description': 'What to do once you wake up. It is handed back to you then.',
                },
                'seconds': {
                    'type': 'integer',
                    'description': f'Seconds to wait, {MIN_DELAY_SECONDS} to {MAX_DELAY_SECONDS}.',
                },
                'until': {
                    'type': 'string',
                    'description': 'ISO 8601 time to wait until, UTC unless it carries an offset.',
                },
                'model': {
                    'type': 'string',
                    'description': 'Model of the record to watch.',
                },
                'record_id': {
                    'type': 'integer',
                    'description': 'Id of the record to watch.',
                },
                'condition': {
                    'type': 'array',
                    'description': (
                        "Domain the watched record must match, e.g. [['payment_state', '=', 'paid']]."
                    ),
                    'items': {},
                },
                'on_message': {
                    'type': 'boolean',
                    'description': 'Wake when a message or email is posted on the watched record.',
                },
            },
            'required': ['note'],
        },
        category='read',
        registry='odoo',
    )
    def _mcp_wait(
        self,
        note: str,
        seconds: int | None = None,
        until: str | None = None,
        model: str | None = None,
        record_id: int | None = None,
        condition: list | None = None,
        on_message: bool = False,
    ) -> dict:
        """Plan the pause of the chat, or answer at once when the condition already holds.

        :raise UserError: when the arguments do not describe a valid wait
        """
        self._check_can_wait()
        note = (note or '').strip()
        if not note or len(note) > MAX_NOTE_CHARS:
            raise UserError(
                self.env._(
                    "'note' must say what to do on waking, in at most %s characters.",
                    MAX_NOTE_CHARS,
                )
            )
        plan = {
            'status': 'waiting',
            'resume_at': fields.Datetime.to_string(self._wait_until(seconds, until)),
            'note': note,
            'record': False,
            'condition': False,
            'on_message': False,
        }
        if not (model or record_id):
            if condition or on_message:
                raise UserError(
                    self.env._(
                        "'condition' and 'on_message' need the 'model' and "
                        "'record_id' of the record to watch."
                    )
                )
            return plan
        record = self._wait_record(model, record_id)
        if not (condition or on_message):
            raise UserError(
                self.env._("Give a 'condition', 'on_message' or both for the record.")
            )
        if on_message and 'message_ids' not in record._fields:
            raise UserError(self.env._('Messages cannot be posted on %s.', model))
        if condition and record.search_count(
            Domain('id', '=', record.id) & Domain(condition), limit=1
        ):
            return {'status': 'condition_met', 'note': note}
        return {
            **plan,
            'record': {
                'model': record._name,
                'id': record.id,
                'name': record.display_name,
            },
            'condition': condition or False,
            'on_message': bool(on_message),
        }
