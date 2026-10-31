from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

MODEL_UPDATES = {
    'model_mistral_large': {
        'name': 'Mistral Large 4',
        'technical_name': 'mistral-large-4',
        'context_window': 1048576,
        'notes': 'Takes no Mistral built-in connectors (web search, code interpreter, image generation); agents that need them run on Mistral Medium 3.5 or Small 4.',
        'input_rate': 0.7,
        'output_rate': 2.1,
        'cache_read_rate': 0.07,
    },
    'model_mistral_medium': {
        'notes': 'Mistral retires Medium 3.5 on 30 April 2027. Its suggested successor, Mistral Large 4, takes no built-in connectors, so Medium stays the default chat and image model until then.',
    },
    'model_zai_glm': {
        'name': 'Z.ai GLM 5.3',
        'technical_name': 'zai-glm-5-3',
    },
}


def migrate(cr: Cursor, version: str) -> None:
    """Move the noupdate catalogue off the models Mistral retires.

    The GLM record keeps its database id under a version-free external id, so
    agents and defaults pointing at it follow it to GLM 5.3.
    """
    cr.execute(
        """
        UPDATE ir_model_data
           SET name = 'model_zai_glm'
         WHERE module = 'muk_ai_mistral' AND name = 'model_zai_glm_5_2'
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, values in MODEL_UPDATES.items():
        record = env.ref(f'muk_ai_mistral.{xml_id}', raise_if_not_found=False)
        if record:
            record.write(values)
