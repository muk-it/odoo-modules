from __future__ import annotations

from odoo.addons.muk_ai.tools.modality import MODALITIES, Modality, chat_cost

MODALITIES['decision'] = Modality('per M tokens', chat_cost)
