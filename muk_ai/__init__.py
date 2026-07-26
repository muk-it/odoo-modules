from __future__ import annotations

from odoo.api import Environment

from . import mcp
from . import models
from . import providers
from . import tools


def _post_init_hook(env: Environment) -> None:
    """Seed each company's default AI provider and agent when unset."""
    provider_id = env.ref('muk_ai.provider_openai').id
    agent_id = env.ref('muk_ai.agent_general').id
    companies = (
        env['res.company']
        .sudo()
        .search(
            [
                '|',
                ('default_ai_provider_id', '=', False),
                ('default_ai_agent_id', '=', False),
            ]
        )
    )
    for company in companies:
        vals = {}
        if not company.default_ai_provider_id:
            vals['default_ai_provider_id'] = provider_id
        if not company.default_ai_agent_id:
            vals['default_ai_agent_id'] = agent_id
        if vals:
            company.write(vals)
