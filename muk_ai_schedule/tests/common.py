from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.muk_ai.tests.common import AITestCommon

USAGE = {'input_tokens': 1, 'output_tokens': 1}


def text_payload(text: str = 'ok') -> dict:
    """Build the provider result of a round that answers with plain text."""
    return {
        'text': text,
        'tool_calls': [],
        'carry_inputs': [
            {
                'type': 'message',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': text}],
            }
        ],
        'usage': dict(USAGE),
    }


def tool_payload(*calls: tuple) -> dict:
    """Build the provider result of a round that calls ``(name, arguments, call_id)``."""
    tool_calls = [
        {'call_id': call_id, 'name': name, 'arguments': arguments}
        for name, arguments, call_id in calls
    ]
    return {
        'text': '',
        'tool_calls': tool_calls,
        'carry_inputs': [
            {
                'type': 'function_call',
                'name': call['name'],
                'arguments': json.dumps(call['arguments']),
                'call_id': call['call_id'],
            }
            for call in tool_calls
        ],
        'usage': dict(USAGE),
    }


class WaitCase(AITestCommon):
    """A chat whose agent pauses itself with the wait tool."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the partner a wait can watch, with no limit on new chats."""
        super().setUpClass()
        cls.provider.sudo().rate_limit = 0
        cls.partner = cls.env['res.partner'].create({'name': 'Acme'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _mock_responses(self, payloads: list) -> Iterator[None]:
        """Answer each provider round with the next payload, raising an exception one."""
        remaining = list(payloads)

        def fake(self_arg, *args, **kwargs) -> dict:
            """Return or raise the next payload."""
            payload = remaining.pop(0)
            if isinstance(payload, Exception):
                raise payload
            return payload

        with patch.object(
            type(self.provider), '_request_responses', autospec=True, side_effect=fake
        ):
            yield

    @contextmanager
    def _capture_bus(self) -> Iterator[list[tuple]]:
        """Collect every bus notification as ``(target, type, message)``."""
        captured = []

        def fake(self_arg, target, notification_type, message) -> None:
            """Record the notification instead of queueing it."""
            captured.append((target, notification_type, message))

        with patch.object(
            type(self.env['bus.bus']), '_sendone', autospec=True, side_effect=fake
        ):
            yield captured

    @contextmanager
    def _hold_lock(self, session_id: int) -> Iterator[None]:
        """Make the advisory lock of a session look taken by another worker."""
        sessions = type(self.env['muk_ai.session'])
        origin = sessions._try_session_lock

        def try_lock(self_arg, key: int) -> bool:
            """Refuse the lock of the held session."""
            return key != session_id and origin(self_arg, key)

        with patch.object(sessions, '_try_session_lock', try_lock):
            yield

    def _session(self) -> models.BaseModel:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': 'Test chat'})

    def _watch(self, **arguments) -> dict:
        """Return wait arguments watching the partner for an hour at most."""
        return {
            'note': 'Check the partner',
            'seconds': 3600,
            'model': 'res.partner',
            'record_id': self.partner.id,
            **arguments,
        }

    def _waiting_chat(self, *extra_calls: tuple, **arguments) -> models.BaseModel:
        """Start a chat whose first round calls wait, then the extra calls."""
        chat = self._session()
        with self._mock_responses(
            [tool_payload(('wait', arguments, 'w1'), *extra_calls)]
        ):
            chat.start('go')
        return chat

    def _run_cron(self, *payloads: dict | Exception) -> None:
        """Run the wake-up cron on what is written, answering the woken rounds."""
        self.env.flush_all()
        with (
            self._mock_responses(list(payloads) or [text_payload('done')]),
            self.enter_registry_test_mode(),
        ):
            self.env['muk_ai.session']._cron_wake_sessions()
        self.env.invalidate_all()

    def _expire(self, chat: models.BaseModel) -> None:
        """Move the wake-up time of the chat into the past."""
        chat.flush_recordset()
        self.env.cr.execute(
            SQL(
                'UPDATE muk_ai_session SET wake_at = %s WHERE id IN %s',
                fields.Datetime.now() - timedelta(seconds=1),
                tuple(chat.ids),
            )
        )
        chat.invalidate_recordset()

    def _outputs_for(self, session: models.BaseModel, call_id: str) -> list:
        """Return the tool outputs the conversation holds for ``call_id``."""
        return [
            item
            for item in session.conversation or []
            if isinstance(item, dict)
            and item.get('type') == 'function_call_output'
            and item.get('call_id') == call_id
        ]

    def _tool_output(self, session: models.BaseModel, call_id: str) -> dict:
        """Return the decoded tool output the conversation holds for ``call_id``."""
        return json.loads(self._outputs_for(session, call_id)[0]['output'])

    def _events(self, session: models.BaseModel, kind: str) -> list:
        """Return the session's transcript events of one kind."""
        events = session.fetch_events(limit=1000)['events']
        return [event for event in events if event['kind'] == kind]
