from __future__ import annotations

from odoo import models

MAX_PROMPT_CHARS = 4000


class PreviousProxy:
    """Read-only view of the previous chat of a record for prompt templates."""

    __slots__ = ('_session',)

    def __init__(self, session: models.BaseModel) -> None:
        """Wrap a chat, empty when there is no previous one."""
        self._session = session

    @property
    def last_text(self) -> str:
        """Return the last answer of the chat."""
        return self._session.last_text or ''

    @property
    def tool_log(self) -> list[dict]:
        """Return the tool calls of the chat with their JSON arguments and output."""
        return [
            {
                'name': log.tool_name or '',
                'arguments': log.request_data or '',
                'output': log.response_data or '',
            }
            for log in self._session.log_ids
        ]
