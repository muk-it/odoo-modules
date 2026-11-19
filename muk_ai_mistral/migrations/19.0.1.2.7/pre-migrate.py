from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Carry the Medium 3.5 image record over to Mistral Large 4, which succeeds it.

    Agents drawing with the record follow it to the successor, which the
    noupdate catalogue would otherwise ship as a second record.
    """
    cr.execute(
        """
        UPDATE muk_ai_model
           SET name = 'Mistral Large 4 Images',
               technical_name = 'mistral-large-4',
               notes = 'Mistral Large 4 driving the image generation connector. '
                       'Mistral bills $0.10 per generated image plus the '
                       'driver''s few hundred prompt and completion tokens at '
                       'the chat rate.'
         WHERE id = (
                SELECT res_id
                  FROM ir_model_data
                 WHERE module = 'muk_ai_mistral'
                   AND name = 'model_mistral_medium_image'
               )
        """
    )
    cr.execute(
        """
        UPDATE ir_model_data
           SET name = 'model_mistral_large_image'
         WHERE module = 'muk_ai_mistral' AND name = 'model_mistral_medium_image'
        """
    )
