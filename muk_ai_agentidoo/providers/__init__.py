from odoo.addons.muk_ai.providers import REGISTRY

from .agentidoo import AgentidooProvider


REGISTRY[AgentidooProvider.name] = AgentidooProvider
