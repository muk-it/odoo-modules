from odoo import fields, models


class AISessionPending(models.Model):

    _name = 'muk_ai.session.pending'
    _description = "AI Session Pending Message"
    _order = 'queued_at, id'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    session_id = fields.Many2one(
        comodel_name='muk_ai.session',
        string="Session",
        required=True,
        index=True,
        ondelete='cascade',
    )

    content = fields.Text(
        string="Content",
    )

    attachment_ids = fields.Json(
        string="Attachment IDs",
    )

    queued_at = fields.Datetime(
        string="Queued At",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _to_payload(self):
        return {
            'id': self.id,
            'content': self.content or '',
            'attachment_ids': self.attachment_ids or [],
            'queued_at': (
                fields.Datetime.to_string(self.queued_at)
                if self.queued_at else None
            ),
        }
