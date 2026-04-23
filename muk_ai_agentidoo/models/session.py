from odoo import fields, models


class AISession(models.Model):

    _inherit = 'muk_ai.session'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    agentidoo_session_id = fields.Char(
        string="Agentidoo Session ID",
        readonly=True,
        copy=False,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _uses_agentidoo(self):
        provider = self._effective_provider()
        return bool(provider) and provider.name == 'agentidoo'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _run_to_completion(self, *args, **kwargs):
        if not self._uses_agentidoo():
            return super()._run_to_completion(*args, **kwargs)
        bag = {'session_id': self.agentidoo_session_id or ''}
        result = super(
            AISession, self.with_context(agentidoo_bag=bag),
        )._run_to_completion(*args, **kwargs)
        new_session_id = bag.get('session_id')
        if new_session_id and new_session_id != self.agentidoo_session_id:
            self.agentidoo_session_id = new_session_id
        return result
