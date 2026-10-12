from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import models
from odoo.tools import SQL

from odoo.addons.muk_ai_automation.tests.common import AutomationTestCommon


def json_response(payload, status_code: int = 200) -> requests.Response:
    """Build an HTTP response carrying ``payload`` as its JSON body."""
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(payload).encode()
    response.headers['Content-Type'] = 'application/json'
    response.url = 'https://provider.test/'
    return response


class DecisionTestCommon(AutomationTestCommon):
    """Partners, scripted provider rounds and scripted HTTP answers for decisions."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _session(self, **values) -> models.BaseModel:
        """Create a chat session owned by the current user."""
        return self.env['muk_ai.session'].create({'name': 'Test chat', **values})

    def _backdate(
        self, records: models.BaseModel, delta: timedelta, *names: str
    ) -> None:
        """Move the given datetime columns of ``records`` ``delta`` into the past."""
        records.flush_recordset()
        for name in names:
            self.env.cr.execute(
                SQL(
                    'UPDATE %s SET %s = %s - %s WHERE id IN %s',
                    SQL.identifier(records._table),
                    SQL.identifier(name),
                    SQL.identifier(name),
                    delta,
                    tuple(records.ids),
                )
            )
        records.invalidate_recordset(list(names))

    @contextmanager
    def _capture_post(self, *responses) -> Iterator[list[tuple[str, dict]]]:
        """Answer each outgoing HTTP POST with the next response, in order.

        A response may be a ``requests.Response``, an exception to raise, or a
        callable taking the request keyword arguments and returning either.
        The yielded list collects every request as ``(url, kwargs)``.
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
