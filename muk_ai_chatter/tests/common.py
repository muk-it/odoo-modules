from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from odoo import models
from odoo.tests import TransactionCase


class ChatterTestCommon(TransactionCase):
    """Shared fixtures for the chatter suites."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Set up a mentionable agent, a record, and a conversation to summon it in."""
        super().setUpClass()
        cls.agent = cls.env['muk_ai.agent'].create({'name': 'Chatter Agent'})
        cls.record = cls.env['res.partner'].create({'name': 'Mentioned Record'})
        cls.channel = cls.env['discuss.channel'].channel_create(
            name='Sales Floor', group_id=None
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _hide(cls, record: models.BaseModel) -> None:
        """Hide ``record`` from everybody but the superuser."""
        cls.env['ir.rule'].create(
            {
                'name': 'Hide one record',
                'model_id': cls.env['ir.model']._get_id(record._name),
                'domain_force': repr([('id', '!=', record.id)]),
            }
        )

    @contextmanager
    def _mute_worker(self) -> Iterator[list]:
        """Capture the prompts sessions are started with, starting none."""
        started = []

        def fake(
            session: models.BaseModel,
            user_message: str | None = None,
            attachment_ids: list[int] | None = None,
        ) -> dict:
            """Record the start instead of running it."""
            started.append((session, user_message))
            return {}

        with patch.object(
            type(self.env['muk_ai.session']), 'start', autospec=True, side_effect=fake
        ):
            yield started

    @contextmanager
    def _mute_dispatch(self) -> Iterator[None]:
        """Let sessions start for real without handing them to a worker."""
        with patch.object(
            type(self.env['muk_ai.session']), '_trigger_worker', autospec=True
        ):
            yield

    def _mention(
        self,
        body: str = 'Summarise this thread',
        record: models.BaseModel | None = None,
    ) -> models.BaseModel:
        """Post a message on a thread mentioning the agent."""
        return (record or self.channel).message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=[self.agent.partner_id.id],
        )

    def _suggested_partner_ids(self, payload: list[dict]) -> list[int]:
        """Return the contact ids a mention suggestion payload offered."""
        return [row['id'] for row in payload]

    def _sessions_on(self, record: models.BaseModel) -> models.BaseModel:
        """Return the sessions linked to ``record``, oldest first."""
        return self.env['muk_ai.session'].search(
            [('res_model', '=', record._name), ('res_id', '=', record.id)],
            order='id',
        )

    def _messages_on(self, record: models.BaseModel) -> models.BaseModel:
        """Return the messages of ``record``, oldest first."""
        return self.env['mail.message'].search(
            [('model', '=', record._name), ('res_id', '=', record.id)],
            order='id',
        )
