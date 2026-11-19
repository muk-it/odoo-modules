from __future__ import annotations

from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Carry the Gemini 3.5 Flash record over to Gemini 3.6 Flash, which serves it.

    Agents and defaults on the record follow it to the successor, which the
    noupdate catalogue would otherwise ship as a second record.
    """
    cr.execute(
        """
        UPDATE muk_ai_model
           SET name = 'Gemini 3.6 Flash',
               technical_name = 'gemini-3.6-flash'
         WHERE id = (
                SELECT res_id
                  FROM ir_model_data
                 WHERE module = 'muk_ai' AND name = 'model_gemini_3_5_flash'
               )
        """
    )
    cr.execute(
        """
        UPDATE ir_model_data
           SET name = 'model_gemini_3_6_flash'
         WHERE module = 'muk_ai' AND name = 'model_gemini_3_5_flash'
        """
    )
