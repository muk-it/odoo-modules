from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

MODEL_UPDATES = {
    'model_mistral_large': ('Mistral Large 3', 0.5, 1.5),
    'model_mistral_medium': ('Mistral Medium 3.5', 1.5, 7.5),
    'model_mistral_small': ('Mistral Small 4', 0.15, 0.6),
    'model_ministral_8b': ('Ministral 3 8B', 0.15, 0.15),
    'model_ministral_3b': ('Ministral 3 3B', 0.1, 0.1),
}


def migrate(cr: Cursor, version: str) -> None:
    """Refresh the noupdate catalogue to the current Mistral generation."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, (name, input_rate, output_rate) in MODEL_UPDATES.items():
        record = env.ref(f'muk_ai_mistral.{xml_id}', raise_if_not_found=False)
        if record:
            record.write(
                {
                    'name': name,
                    'input_rate': input_rate,
                    'output_rate': output_rate,
                }
            )
