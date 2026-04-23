from . import mcp
from . import models
from . import providers
from . import tools


def _post_init_hook(env):
    vals = {
        'default_ai_provider_id': env.ref('muk_ai.provider_openai').id,
        'default_ai_agent_id': env.ref('muk_ai.agent_general').id,
    }
    for company in env['res.company'].sudo().search([
        ('default_ai_provider_id', '=', False),
        ('default_ai_agent_id', '=', False),
    ]):
        company.write(vals)
