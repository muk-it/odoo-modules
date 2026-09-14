from __future__ import annotations

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    """Point the shipped provider at the image model this version seeds.

    The provider is ``noupdate`` data, so an upgrade leaves its new
    ``default_image_model_id`` empty and agents without a pick would draw
    with another vendor.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    provider = env.ref('muk_ai_mistral.provider_mistral', raise_if_not_found=False)
    model = env.ref(
        'muk_ai_mistral.model_mistral_medium_image', raise_if_not_found=False
    )
    if provider and model and not provider.default_image_model_id:
        provider.default_image_model_id = model
