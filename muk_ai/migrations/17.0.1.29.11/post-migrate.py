from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

FLASH_PROMO = (
    'Promotional pricing through 2026-12-31. From 2027-01-01 Google bills '
    '$1.50 input, $7.50 output and $0.15 cached input per million tokens.'
)

MODEL_UPDATES = {
    'model_gpt_6_astra': {'cache_write_rate': 12.5},
    'model_gpt_5_6_sol': {
        'cache_write_rate': 5.0,
        'notes': 'OpenAI lists these rates as promotional pricing until 2026-11-30.',
    },
    'model_gpt_5_6_terra': {'cache_write_rate': 2.5},
    'model_gpt_5_6_luna': {'cache_write_rate': 0.25},
    'model_gpt_5_5': {'reasoning_efforts': ['low', 'medium', 'high', 'xhigh']},
    'model_gemini_3_6_flash': {
        'context_window': 1048576,
        'reasoning_efforts': ['minimal', 'low', 'medium', 'high'],
        'notes': FLASH_PROMO,
        'input_rate': 0.75,
        'output_rate': 3.75,
        'cache_read_rate': 0.075,
    },
    'model_gemini_3_5_flash_lite': {
        'reasoning_efforts': ['minimal', 'low', 'medium', 'high'],
    },
    'model_gemini_3_1_flash_image': {
        'notes': (
            'Rate is for a 1K output image. Google bills $0.045 at 0.5K, $0.101 '
            'at 2K and $0.151 at 4K, plus the text prompt at $0.50 input and '
            '$3.00 output per million tokens.'
        ),
    },
}

REMOVED_MODELS = [
    'model_gpt_5_4_nano',
    'model_gpt_5_1',
    'model_gpt_4_1',
    'model_gpt_4_1_mini',
    'model_gpt_4o',
    'model_gpt_4o_mini',
    'model_gpt_image_2',
    'model_gpt_image_1_5',
    'model_claude_opus_4_5',
    'model_claude_sonnet_4_5',
    'model_gemini_3_1_flash_lite',
    'model_gemini_2_5_pro',
    'model_gemini_2_5_flash',
    'model_gemini_2_5_flash_lite',
]

SUPERSEDED_DEFAULTS = [
    ('provider_openai', 'chat', 'model_gpt_5_6_terra', 'model_gpt_6_1_terra'),
    ('provider_openai', 'image', 'model_gpt_image_2', 'model_gpt_image_2_6_flare'),
    ('provider_anthropic', 'chat', 'model_claude_sonnet_5', 'model_claude_sonnet_5_5'),
    ('provider_google', 'chat', 'model_gemini_3_8_flash', 'model_gemini_4_hydrogen'),
    (
        'provider_google',
        'image',
        'model_gemini_3_1_flash_image',
        'model_gemini_nano_banana_2_1',
    ),
]


def migrate(cr: Cursor, version: str) -> None:
    """Sync the noupdate catalogue with the current provider line-ups.

    Refresh the survivors, move a provider default to the successor while it
    is unset, the shipped one or a model being dropped, then drop the models
    the vendors retire. Agents on a dropped model fall back to the default.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, values in MODEL_UPDATES.items():
        if record := env.ref(f'muk_ai.{xml_id}', raise_if_not_found=False):
            record.write(values)
    removed = env['muk_ai.model']
    for xml_id in REMOVED_MODELS:
        removed |= env.ref(f'muk_ai.{xml_id}', raise_if_not_found=False) or removed
    for provider_id, modality, shipped, current in SUPERSEDED_DEFAULTS:
        provider = env.ref(f'muk_ai.{provider_id}', raise_if_not_found=False)
        model = env.ref(f'muk_ai.{current}', raise_if_not_found=False)
        previous = env.ref(f'muk_ai.{shipped}', raise_if_not_found=False)
        if not (provider and model):
            continue
        default = provider[f'default_{modality}_model_id']
        if not default or default == previous or default in removed:
            provider[f'default_{modality}_model_id'] = model
    removed.unlink()
