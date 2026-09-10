from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

CONTEXT_UPDATES = {
    'model_mistral_large': 262144,
    'model_mistral_medium': 262144,
    'model_mistral_small': 262144,
    'model_ministral_14b': 262144,
    'model_ministral_8b': 262144,
    'model_ministral_3b': 131072,
    'model_codestral': 256000,
}

REMOVED_MODELS = [
    'model_magistral_medium',
    'model_magistral_small',
]


def migrate(cr: Cursor, version: str) -> None:
    """Align the noupdate catalogue with the context windows Mistral reports.

    ``GET /v1/models`` is the authority here: every generalist runs at
    262,144 tokens, Ministral 3 3B at 131,072 and Codestral at 256,000 —
    not the rounded figures the catalogue shipped. Magistral is dropped for
    good: both names are now aliases of Mistral Medium 3.5 and Small 4, so
    they were duplicate entries priced as if they were separate models.
    Agents pointing at a dropped model fall back to the company default via
    the ``ondelete='set null'`` on ``muk_ai.agent.model_id``.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, context_window in CONTEXT_UPDATES.items():
        record = env.ref(f'muk_ai_mistral.{xml_id}', raise_if_not_found=False)
        if record:
            record.context_window = context_window
    for xml_id in REMOVED_MODELS:
        record = env.ref(f'muk_ai_mistral.{xml_id}', raise_if_not_found=False)
        if record:
            record.unlink()
