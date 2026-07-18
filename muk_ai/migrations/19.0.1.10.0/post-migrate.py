from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

FULL_RANGE = ['minimal', 'low', 'medium', 'high', 'xhigh', 'max']
ADAPTIVE_RANGE = ['low', 'medium', 'high', 'xhigh', 'max']

REASONING_EFFORTS = {
    'model_gpt_5_5_pro': (['medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_4_pro': (['medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_5': (['low', 'medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_4': (['low', 'medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_4_mini': (['low', 'medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_4_nano': (['low', 'medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_2': (['low', 'medium', 'high', 'xhigh'], 'medium'),
    'model_gpt_5_1': (['low', 'medium', 'high'], 'medium'),
    'model_gpt_5': (['minimal', 'low', 'medium', 'high'], 'medium'),
    'model_gpt_5_mini': (['minimal', 'low', 'medium', 'high'], 'medium'),
    'model_gpt_5_nano': (['minimal', 'low', 'medium', 'high'], 'medium'),
    'model_o1': (['low', 'medium', 'high'], 'medium'),
    'model_o3': (['low', 'medium', 'high'], 'medium'),
    'model_o3_mini': (['low', 'medium', 'high'], 'medium'),
    'model_o4_mini': (['low', 'medium', 'high'], 'medium'),
    'model_claude_fable_5': (ADAPTIVE_RANGE, 'medium'),
    'model_claude_opus_4_8': (ADAPTIVE_RANGE, 'medium'),
    'model_claude_opus_4_7': (ADAPTIVE_RANGE, 'medium'),
    'model_claude_opus_4_6': (FULL_RANGE, 'medium'),
    'model_claude_opus_4_5': (FULL_RANGE, 'medium'),
    'model_claude_opus_4_1': (FULL_RANGE, 'medium'),
    'model_claude_sonnet_4_6': (FULL_RANGE, 'medium'),
    'model_claude_sonnet_4_5': (FULL_RANGE, 'medium'),
    'model_claude_sonnet_4': (FULL_RANGE, 'medium'),
    'model_claude_3_7_sonnet': (FULL_RANGE, 'medium'),
    'model_gemini_3_1_pro_preview': (['low', 'medium', 'high'], False),
    'model_gemini_3_5_flash': (['low', 'high'], False),
    'model_gemini_3_1_flash_lite': (['low', 'high'], False),
    'model_gemini_3_flash_preview': (['low', 'high'], False),
}


def migrate(cr: Cursor, version: str) -> None:
    """Seed reasoning effort capabilities on the noupdate model catalogue."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, (efforts, default) in REASONING_EFFORTS.items():
        record = env.ref(f'muk_ai.{xml_id}', raise_if_not_found=False)
        if record:
            record.write(
                {
                    'reasoning_efforts': efforts,
                    'reasoning_effort_default': default,
                }
            )
