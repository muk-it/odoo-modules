from odoo.addons.muk_ai.providers import REGISTRY

from .mistral import MistralProvider


REGISTRY[MistralProvider.name] = MistralProvider
