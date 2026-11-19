from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

MODEL_UPDATES = {
    'model_mistral_large': {
        'notes': False,
        'reasoning_efforts': ['low', 'medium', 'high'],
        'reasoning_effort_default': 'medium',
    },
    'model_ministral_3b': {'context_window': 262144},
    'model_codestral': {'context_window': 131072},
    'model_zai_glm': {
        'notes': (
            'Third-party open model from Z.ai, served by Mistral on the same '
            "infrastructure and under the same regional controls as Mistral's "
            'own models. Text only, no vision. Chat, function calling and '
            'structured output are documented; the Mistral built-in connectors '
            '(web search, code interpreter, image generation) are not.'
        ),
        'reasoning_efforts': ['low', 'high', 'max'],
    },
}


def migrate(cr: Cursor, version: str) -> None:
    """Move the noupdate catalogue off Mistral Medium 3.5, which Mistral retires.

    Mistral Large 4 takes over as the default chat model while the default is
    unset or Medium; agents on Medium fall back to the default.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, values in MODEL_UPDATES.items():
        if record := env.ref(f'muk_ai_mistral.{xml_id}', raise_if_not_found=False):
            record.write(values)
    provider = env.ref('muk_ai_mistral.provider_mistral', raise_if_not_found=False)
    large = env.ref('muk_ai_mistral.model_mistral_large', raise_if_not_found=False)
    medium = env.ref('muk_ai_mistral.model_mistral_medium', raise_if_not_found=False)
    if provider and large:
        default = provider.default_chat_model_id
        if not default or default == medium:
            provider.default_chat_model_id = large
    if medium:
        medium.unlink()
