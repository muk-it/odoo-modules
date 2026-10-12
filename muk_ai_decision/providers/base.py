from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.muk_ai.providers.base import ProviderBase


def elapsed_ms(started: float) -> int:
    """Return the milliseconds passed since the monotonic clock read ``started``."""
    return int((time.monotonic() - started) * 1000)


class DecisionProviderBase:
    """Decision transport over a configured ``muk_ai.provider`` account.

    An adapter answers ``decide(model, state, questions)`` in the System One
    shape: the served ``model``, the typed ``answers`` keyed like the
    questions, and the token ``usage``.
    """

    name = ''

    def __init__(self, provider: models.BaseModel) -> None:
        """Bind to the provider record and its region-aware HTTP client."""
        self.provider = provider
        self.client: ProviderBase = provider._get_client()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run_parallel(self, run: Callable, states: list) -> list:
        """Map ``run`` over the states on as many threads as the provider allows."""
        workers = min(max(self.provider.decision_parallel, 1), len(states))
        if workers < 2:
            return [run(state) for state in states]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(run, states))

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def decide(self, model: str, state, questions: dict) -> dict:
        """Answer the typed ``questions`` about ``state`` with ``model``.

        :raise UserError: when the request fails or the answer is malformed
        """
        raise NotImplementedError

    def decide_many(self, model: str, states: list, questions: dict) -> list[tuple]:
        """Answer each state in turn.

        :return: per state, the response or its :class:`UserError`, and the
            milliseconds it took
        """
        outcomes = []
        for state in states:
            started = time.monotonic()
            try:
                outcome = self.decide(model, state, questions)
            except UserError as error:
                outcome = error
            outcomes.append((outcome, elapsed_ms(started)))
        return outcomes
