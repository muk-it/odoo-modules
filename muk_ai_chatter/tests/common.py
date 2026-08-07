from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from odoo import models
from odoo.tests.common import TransactionCase


class ChatterTestCommon(TransactionCase):
    """Shared fixtures for the chatter mention suites."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up a mentionable agent, a record, and a conversation to summon it in."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Chatter Agent'})
        cls.record = cls.env['res.partner'].create({'name': 'Mentioned Record'})
        cls.channel = cls.env['discuss.channel']._create_channel(
            name='Sales Floor', group_id=None
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @contextmanager
    def _mute_worker(self) -> Iterator[list]:
        """Stop sessions from reaching a provider and collect the prompts.

        The mention path is what is under test, not the language model, so the
        turn is captured at ``start`` and never dispatched.
        """
        started = []

        def fake(session_arg, user_message=None, attachment_ids=None):
            started.append((session_arg, user_message))
            return {}

        with patch.object(
            type(self.env['muk_ai.session']),
            'start',
            autospec=True,
            side_effect=fake,
        ):
            yield started

    @contextmanager
    def _mute_dispatch(self) -> Iterator[None]:
        """Let a session start for real, without handing it to a worker.

        Unlike :meth:`_mute_worker`, ``start`` itself runs — it is what names
        the session and builds its first turn — and only the dispatch to a
        provider is held back.
        """
        with patch.object(
            type(self.env['muk_ai.session']),
            '_trigger_worker',
            autospec=True,
            side_effect=lambda session_arg: None,
        ):
            yield

    def _mention(
        self,
        body: str = 'Summarise this thread',
        record: models.BaseModel | None = None,
    ) -> models.BaseModel:
        """Post a message on the thread mentioning the agent."""
        target = record if record is not None else self.record
        return target.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=[self.agent.partner_id.id],
        )

    def _suggested_partner_ids(self, payload: dict | list) -> list[int]:
        """Return the contact ids a mention suggestion payload offered.

        Read out of the store payload rather than matched in its text: the
        repr of a dict quotes its keys whichever way Python feels like, so a
        substring assertion on it can pass while proving nothing.
        """
        if not payload:
            return []
        return [record['id'] for record in payload.get('res.partner', [])]

    def _sessions_on(self, record: models.BaseModel) -> models.BaseModel:
        """Return the sessions linked to ``record``, oldest first."""
        return self.env['muk_ai.session'].search(
            [('res_model', '=', record._name), ('res_id', '=', record.id)],
            order='id',
        )

    def _messages_on(self, record: models.BaseModel) -> models.BaseModel:
        """Return the chatter messages of ``record``, oldest first."""
        return self.env['mail.message'].search(
            [('model', '=', record._name), ('res_id', '=', record.id)],
            order='id',
        )
