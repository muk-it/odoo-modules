from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

MODEL_UPDATES = {
    'model_gpt_5_6_sol': {
        'context_window': 1050000,
        'input_rate': 4.0,
        'output_rate': 20.0,
        'cache_read_rate': 0.4,
    },
    'model_gpt_5_6_terra': {
        'context_window': 1050000,
        'input_rate': 2.0,
        'output_rate': 12.0,
        'cache_read_rate': 0.2,
    },
    'model_gpt_5_6_luna': {
        'context_window': 1050000,
        'input_rate': 0.2,
        'output_rate': 1.2,
        'cache_read_rate': 0.02,
    },
    'model_gpt_5_5': {
        'context_window': 1050000,
        'reasoning_efforts': ['low', 'medium', 'high', 'xhigh', 'max'],
    },
    'model_gpt_5_5_pro': {'context_window': 1050000},
    'model_gpt_5_4': {'context_window': 1050000},
    'model_gpt_5_4_pro': {'context_window': 1050000},
    'model_claude_opus_4_6': {
        'reasoning_efforts': ['low', 'medium', 'high', 'max'],
    },
    'model_claude_opus_4_5': {
        'reasoning_efforts': ['low', 'medium', 'high'],
    },
    'model_claude_sonnet_5': {
        'input_rate': 2.0,
        'output_rate': 10.0,
        'cache_read_rate': 0.2,
        'cache_write_rate': 2.5,
        'notes': False,
    },
    'model_claude_sonnet_4_6': {
        'reasoning_efforts': ['low', 'medium', 'high', 'max'],
    },
    'model_claude_sonnet_4_5': {
        'reasoning_efforts': False,
        'reasoning_effort_default': False,
        'notes': (
            'No retirement announced. The minimum availability commitment '
            'from Anthropic runs to 2026-09-29; Claude Sonnet 5 is the '
            'successor.'
        ),
    },
    'model_gemini_3_5_flash': {
        'context_window': 1048576,
        'reasoning_efforts': ['low', 'medium', 'high'],
    },
    'model_gemini_3_1_pro_preview': {
        'context_window': 1048576,
        'notes': (
            'Rates apply to prompts up to 200,000 tokens. Above that Google '
            'bills $4.00 input, $18.00 output and $0.40 cached input per '
            'million tokens.'
        ),
    },
    'model_gemini_3_1_flash_lite': {
        'context_window': 1048576,
        'reasoning_efforts': ['low', 'medium', 'high'],
        'notes': (
            'Google lists 2027-05-07 as the earliest shutdown date. '
            'Successor is Gemini 3.5 Flash Lite.'
        ),
    },
    'model_gemini_2_5_pro': {
        'context_window': 1048576,
        'cache_read_rate': 0.125,
        'notes': (
            'Rates apply to prompts up to 200,000 tokens. Above that Google '
            'bills $2.50 input, $15.00 output and $0.25 cached input per '
            'million tokens.'
        ),
    },
    'model_gemini_2_5_flash': {
        'context_window': 1048576,
        'cache_read_rate': 0.03,
    },
    'model_gemini_2_5_flash_lite': {
        'context_window': 1048576,
        'cache_read_rate': 0.01,
    },
}

REMOVED_MODELS = [
    'model_gpt_5',
    'model_gpt_5_mini',
    'model_gpt_5_nano',
    'model_gpt_4_1_nano',
    'model_o1',
    'model_o1_mini',
    'model_o3',
    'model_o3_mini',
    'model_o4_mini',
    'model_claude_opus_4_1',
    'model_claude_opus_4',
    'model_claude_sonnet_4',
    'model_claude_haiku_3_5',
    'model_claude_3_7_sonnet',
    'model_gemini_3_flash_preview',
    'model_gemini_2_5_flash_image',
]

SUPERSEDED_DEFAULTS = {
    'provider_openai': ('model_gpt_5_4', 'model_gpt_5_6_terra'),
    'provider_anthropic': ('model_claude_sonnet_4_6', 'model_claude_sonnet_5'),
    'provider_google': ('model_gemini_3_5_flash', 'model_gemini_3_8_flash'),
}


def migrate(cr: Cursor, version: str) -> None:
    """Sync the noupdate catalogue with the current provider line-ups.

    The catalogue ships as ``noupdate`` data, so an upgrade never reaches
    the records already in the database: they would keep billing at prices
    the providers have since cut and keep offering models that have been
    retired. Refresh the survivors, drop the retired ones, and move a
    provider default forward only while it still points at the model this
    module used to ship — a default an administrator picked themselves is
    left alone. Agents on a dropped model fall back to the company default
    via the ``ondelete='set null'`` on ``muk_ai.agent.model_id``.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, values in MODEL_UPDATES.items():
        record = env.ref(f'muk_ai.{xml_id}', raise_if_not_found=False)
        if record:
            record.write(values)
    for provider_xml_id, (shipped, current) in SUPERSEDED_DEFAULTS.items():
        provider = env.ref(f'muk_ai.{provider_xml_id}', raise_if_not_found=False)
        model = env.ref(f'muk_ai.{current}', raise_if_not_found=False)
        previous = env.ref(f'muk_ai.{shipped}', raise_if_not_found=False)
        current_default = provider.default_model_id if provider else None
        if provider and model and (not current_default or current_default == previous):
            provider.default_model_id = model
    for xml_id in REMOVED_MODELS:
        record = env.ref(f'muk_ai.{xml_id}', raise_if_not_found=False)
        if record:
            record.unlink()
