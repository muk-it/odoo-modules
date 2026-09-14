from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

SHIPPED_IMAGE_DEFAULTS = {
    'provider_openai': 'model_gpt_image_2',
    'provider_google': 'model_gemini_3_1_flash_image',
}


def migrate(cr: Cursor, version: str) -> None:
    """Point the shipped providers at the image models this version seeds.

    The providers are ``noupdate`` data, so an upgrade leaves their new
    ``default_image_model_id`` empty; Google renders images through that
    model and would lose image output until an administrator picks one.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    for provider_xml_id, model_xml_id in SHIPPED_IMAGE_DEFAULTS.items():
        provider = env.ref(f'muk_ai.{provider_xml_id}', raise_if_not_found=False)
        model = env.ref(f'muk_ai.{model_xml_id}', raise_if_not_found=False)
        if provider and model and not provider.default_image_model_id:
            provider.default_image_model_id = model
