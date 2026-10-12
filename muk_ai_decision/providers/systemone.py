from __future__ import annotations

import time

import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.base import ProviderBase
from odoo.addons.muk_ai.providers.region import CUSTOM
from odoo.addons.muk_ai_decision.providers.base import DecisionProviderBase, elapsed_ms

MAX_RETRIES = 3
MAX_RETRY_DELAY = 10.0
RETRY_STATUS = frozenset({429, 503, 529})

CONNECTION_QUESTIONS = {
    'ok': {'type': 'noul', 'instructions': 'Does the text say ok?'},
}


def retry_delay(response: requests.Response, attempt: int) -> float:
    """Return the seconds to wait before retrying, as the server asks or doubling."""
    try:
        delay = float(response.headers.get('Retry-After') or 0)
    except ValueError:
        delay = 0.0
    return min(delay or 0.5 * 2**attempt, MAX_RETRY_DELAY)


class SystemOneProvider(ProviderBase):
    """Any server speaking the System One decision API, hosted or self-hosted."""

    name = 'systemone'
    label = 'System One Compatible'
    default_model = 'jev-latest'
    default_url = 'https://api.typesafe.ai'
    regions = (CUSTOM,)
    modalities = frozenset({'decision'})

    supports_vision = False

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def authenticated(self) -> bool:
        """Report the account ready with a key, or as a self-hosted server."""
        return super().authenticated or self.provider.sudo().api_region == CUSTOM.code

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def headers(self) -> dict:
        """Return the JSON request headers, with the bearer token when a key is set."""
        headers = {'Content-Type': 'application/json'}
        if key := self._api_key:
            headers['Authorization'] = f'Bearer {key}'
        return headers

    def model_for(self, override: str | None = None) -> str:
        """Return the override, the default decision model, or the class default."""
        return (
            override
            or self.provider._default_model('decision').technical_name
            or self.default_model
        )

    def test_connection(self) -> bool:
        """Answer one yes/no question to verify the endpoint responds."""
        SystemOneDecisionProvider(self.provider).decide(
            self.model_for(), 'ok', CONNECTION_QUESTIONS
        )
        return True


class SystemOneDecisionProvider(DecisionProviderBase):
    """Answer decisions through the System One ``/v1/systemone`` route."""

    name = 'systemone'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _error(self, error) -> UserError:
        """Return the user-facing error the client raises for ``error``."""
        try:
            self.client._raise(error)
        except UserError as exc:
            return exc

    def _outcome(self, response) -> dict | UserError:
        """Return the System One answer of a raw response, or the error it carries."""
        if isinstance(response, Exception):
            return self._error(response)
        if not response.ok:
            return self._error(response.text or response.reason)
        try:
            payload = response.json()
        except ValueError as error:
            return self._error(error)
        if not isinstance(payload, dict) or not isinstance(
            payload.get('answers'), dict
        ):
            return self._error(_('no answers returned'))
        return payload

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def decide(self, model: str, state, questions: dict) -> dict:
        """POST the questions and return the System One response.

        :raise UserError: when the request fails or carries no answers
        """
        ((outcome, _duration),) = self.decide_many(model, [state], questions)
        if isinstance(outcome, UserError):
            raise outcome
        return outcome

    def decide_many(self, model: str, states: list, questions: dict) -> list[tuple]:
        """POST the states concurrently, retrying a busy or rate-limited server.

        Only the HTTP round trips leave the worker thread; the endpoint, the
        headers and the error handling stay with the provider record.
        """
        url = f'{self.client.api_url}/v1/systemone'
        headers = self.client.headers()
        timeout = self.provider.request_timeout
        session = self.client._http_session()

        def post(state) -> tuple:
            """POST one state, pairing the response or transport error with its duration."""
            started = time.monotonic()
            body = {'model': model, 'state': state, 'questions': questions}
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = session.post(
                        url, headers=headers, json=body, timeout=timeout
                    )
                except requests.RequestException as error:
                    return error, elapsed_ms(started)
                if response.status_code not in RETRY_STATUS or attempt == MAX_RETRIES:
                    break
                time.sleep(retry_delay(response, attempt))
            return response, elapsed_ms(started)

        return [
            (self._outcome(response), duration)
            for response, duration in self._run_parallel(post, states)
        ]
