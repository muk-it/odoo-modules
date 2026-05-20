from odoo import fields, models


class ResConfigSettings(models.TransientModel):

    _inherit = 'res.config.settings'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    ai_provider_id = fields.Many2one(
        related='company_id.default_ai_provider_id',
        readonly=False,
    )

    ai_agent_id = fields.Many2one(
        related='company_id.default_ai_agent_id',
        readonly=False,
    )

    module_muk_ai_compat = fields.Boolean(
        string='MuK AI Compatible Providers',
        help='Ollama, vLLM, OpenRouter and every OpenAI-compatible LLM.',
    )

    module_muk_ai_schedule = fields.Boolean(
        string='MuK AI Schedule',
        help='Run agents on a schedule, let them pause and resume themselves.',
    )

    module_muk_ai_skills = fields.Boolean(
        string='MuK AI Skills',
        help='Pre-built agent skills the user or LLM can switch into.',
    )

    module_muk_ai_voice = fields.Boolean(
        string='MuK AI Voice',
        help='Talk to the assistant: realtime STT and spoken replies via TTS.',
    )
