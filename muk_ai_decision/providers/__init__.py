from __future__ import annotations

from odoo.addons.muk_ai.providers import REGISTRY as PROVIDERS

from .base import DecisionProviderBase
from .llm import LLMDecisionProvider
from .systemone import SystemOneDecisionProvider, SystemOneProvider

PROVIDERS[SystemOneProvider.name] = SystemOneProvider

REGISTRY = {cls.name: cls for cls in (SystemOneDecisionProvider,)}
