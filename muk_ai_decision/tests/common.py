from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import requests

from odoo import fields, models

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
    """Script the HTTP answers of decision servers and age decision logs."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

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

    def _backdate(self, records: models.BaseModel, delta: timedelta, name: str) -> None:
        """Move the datetime column ``name`` of ``records`` ``delta`` into the past."""
        records.flush_recordset()
        self.env.cr.execute(
            f'UPDATE {records._table} SET {name} = %s WHERE id IN %s',
            (fields.Datetime.now() - delta, tuple(records.ids)),
        )
        records.invalidate_recordset()
