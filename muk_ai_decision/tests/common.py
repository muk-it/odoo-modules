from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields, models
from odoo.tools import SQL

from odoo.addons.muk_ai.tests.common import AITestCommon

USAGE = {'input_tokens': 10, 'output_tokens': 5}


def text_payload(text: str = 'ok') -> dict:
    """Build the provider result of a round that answers with plain text."""
    return {'text': text, 'tool_calls': [], 'carry_inputs': [], 'usage': dict(USAGE)}


def json_response(payload, status_code: int = 200) -> requests.Response:
    """Build an HTTP response carrying ``payload`` as its JSON body."""
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(payload).encode()
    response.headers['Content-Type'] = 'application/json'
    response.url = 'https://provider.test/'
    return response


class DecisionTestCommon(AITestCommon):
    """Keyed providers, worker cursors inside the test and the HTTP boundary fakes."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Activate the shipped chat providers and route worker cursors into the test."""
        super().setUpClass()
        cls.registry_enter_test_mode_cls()
        (cls.provider | cls.provider_anthropic | cls.provider_google).write(
            {'active': True, 'rate_limit': 0}
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, **values) -> models.BaseModel:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': 'Test chat', **values})

    def _domain_for(self, records: models.BaseModel) -> str:
        """Return a domain string matching ``records`` by id."""
        return f"[('id', 'in', {records.ids})]"

    @contextmanager
    def _mock_responses(
        self, payloads: list[dict], repeat_last: bool = False
    ) -> Iterator[list[dict]]:
        """Answer each provider round with the next payload, yielding every request."""
        remaining = list(payloads)
        captured = []

        def fake(self_arg, **kwargs) -> dict:
            """Record the request and return the next scripted payload."""
            captured.append(kwargs)
            if not remaining:
                msg = 'No more mocked provider responses'
                raise AssertionError(msg)
            if repeat_last and len(remaining) == 1:
                return remaining[0]
            return remaining.pop(0)

        with patch.object(
            type(self.env['muk_ai.provider']),
            '_request_responses',
            autospec=True,
            side_effect=fake,
        ):
            yield captured

    @contextmanager
    def _capture_post(self, *responses) -> Iterator[list[tuple[str, dict]]]:
        """Answer each outgoing HTTP POST with the next response, in order.

        A response may be a ``requests.Response``, an exception to raise, or a
        callable taking the request keyword arguments and returning either.
        """
        remaining = list(responses)
        captured = []

        def fake(self_arg, url, **kwargs) -> requests.Response:
            """Record the request and return the next scripted response."""
            captured.append((url, kwargs))
            if not remaining:
                msg = f'No more mocked HTTP responses for {url}'
                raise AssertionError(msg)
            answer = remaining.pop(0)
            if callable(answer) and not isinstance(answer, requests.Response):
                answer = answer(kwargs)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch.object(requests.Session, 'post', autospec=True, side_effect=fake):
            yield captured

    def _backdate(
        self, records: models.BaseModel, delta: timedelta, *names: str
    ) -> None:
        """Move the given datetime columns of ``records`` ``delta`` into the past."""
        records.flush_recordset()
        when = fields.Datetime.now() - delta
        for name in names:
            self.env.cr.execute(
                SQL(
                    'UPDATE %s SET %s = %s WHERE id IN %s',
                    SQL.identifier(records._table),
                    SQL.identifier(name),
                    when,
                    tuple(records.ids),
                )
            )
        records.invalidate_recordset()
