from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from odoo import models


class Modality(NamedTuple):
    """Billing profile of a model modality: what one rate buys, and how to price it.

    An addon adds a modality by extending ``muk_ai.model.modality`` with
    ``selection_add`` and inserting its profile into :data:`MODALITIES`.
    """

    unit: str
    cost: Callable[[models.BaseModel, dict], tuple[float, float]]


def chat_cost(model: models.BaseModel, usage: dict) -> tuple[float, float]:
    """Price token usage: fresh, cache-read and cache-written input plus output.

    ``input_tokens`` is the full prompt; cache-read and cache-write tokens are
    subsets of it billed at their own rates, with the fresh input rate as the
    fallback when a cache rate is unset. Every rate is per million tokens.
    """
    input_tokens = int(usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('output_tokens') or 0)
    cache_read_tokens = int(usage.get('cache_read_tokens') or 0)
    cache_write_tokens = int(usage.get('cache_write_tokens') or 0)
    cache_read_rate = model.cache_read_rate or model.input_rate
    cache_write_rate = model.cache_write_rate or model.input_rate
    fresh_tokens = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
    input_cost = (
        fresh_tokens * model.input_rate
        + cache_read_tokens * cache_read_rate
        + cache_write_tokens * cache_write_rate
    )
    return input_cost / 1_000_000, output_tokens * model.output_rate / 1_000_000


def image_cost(model: models.BaseModel, usage: dict) -> tuple[float, float]:
    """Price generated images at ``output_rate`` each; the prompt is free."""
    return 0.0, int(usage.get('images') or 0) * model.output_rate


MODALITIES: dict[str, Modality] = {
    'chat': Modality('per M tokens', chat_cost),
    'image': Modality('per image', image_cost),
}
