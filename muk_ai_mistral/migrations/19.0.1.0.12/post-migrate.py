from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

CONTEXT_UPDATES = {
    'model_mistral_large': 256000,
    'model_mistral_medium': 256000,
    'model_mistral_small': 256000,
    'model_ministral_14b': 256000,
    'model_ministral_8b': 256000,
    'model_ministral_3b': 256000,
    'model_codestral': 128000,
}

REMOVED_MODELS = [
    'model_pixtral_large',
    'model_magistral_medium',
    'model_magistral_small',
    'model_open_mistral_nemo',
]


def migrate(cr: Cursor, version: str) -> None:
    """Sync the noupdate catalogue with the current Mistral generation.

    Refresh context windows on the surviving models and drop the models
    Mistral retired (Pixtral Large, Magistral, Mistral Nemo). Agents
    pointing at a dropped model fall back to the company default via the
    ``ondelete='set null'`` on ``muk_ai.agent.model_id``.
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
