from __future__ import annotations

from datetime import timedelta

from odoo import models

from odoo.addons.muk_ai.tests.common import AITestCommon, text_payload, tool_payload


class WaitCase(AITestCommon):
    """A chat whose agent pauses itself with the wait tool."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Create the partner a wait can watch."""
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Acme'})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

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
        with self._mock_responses(list(payloads) or [text_payload('done')]):
            self.env['muk_ai.session']._cron_wake_sessions()
        self.env.invalidate_all()

    def _expire(self, chat: models.BaseModel) -> None:
        """Move the wake-up time of the chat into the past."""
        self._backdate(chat, timedelta(seconds=1), 'wake_at')
