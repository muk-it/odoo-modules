from odoo import api, fields, models
from odoo.tools.rendering_tools import (
    parse_inline_template,
    render_inline_template,
    template_env_globals,
)


class AIPromptMixin(models.AbstractModel):

    _name = 'muk_ai.prompt.mixin'
    _description = "AI Prompt Renderer"

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _prompt_eval_context(self):
        return {
            'env': self.env,
            'user': self.env.user,
            'company': self.env.company,
            'ctx': self.env.context,
            'today': fields.Date.context_today(self).isoformat(),
            **template_env_globals,
        }

    def _render_prompt_safe(self, raw, **add_context):
        eval_ctx = self._prompt_eval_context()
        if add_context:
            eval_ctx.update(add_context)
        try:
            return (
                render_inline_template(
                    parse_inline_template(raw), eval_ctx
                ),
                None,
            )
        except Exception as exc:
            return (raw, str(exc))

    def _render_prompt(self, raw, **add_context):
        return self._render_prompt_safe(raw or '', **add_context)[0]
