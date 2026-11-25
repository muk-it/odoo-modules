from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from odoo import api, fields, models


class MCPAccessConfirmation(models.TransientModel):
    """A question a client was sent, until its answer arrives."""

    _name = 'muk_mcp_access.confirmation'
    _description = 'MCP Confirmation'

    # ----------------------------------------------------------
    # Properties
    # ----------------------------------------------------------

    @property
    def MINUTES(self) -> int:
        """Return how long a question can be answered."""
        return 15

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    token = fields.Char(
        string='Token',
        required=True,
        index=True,
    )

    digest = fields.Char(
        string='Digest',
        help='Hash of the user, the key and the call the question is about.',
        required=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @api.model
    def _get_digest(self, principal: str, name: str, arguments: Any) -> str:
        """Hash what an answer is bound to: who calls which tool with what."""
        call = json.dumps([self.env.uid, principal, name, arguments], sort_keys=True)
        return hashlib.sha256(call.encode()).hexdigest()

    @api.model
    def _ask(self, token: str, digest: str) -> None:
        """Keep a question that was sent to the client."""
        self.sudo().create({'token': token, 'digest': digest})

    @api.model
    def _redeem(self, token: Any, digest: str) -> bool:
        """Return whether the question is open for this call, and close it."""
        if not isinstance(token, str):
            return False
        since = fields.Datetime.now() - timedelta(minutes=self.MINUTES)
        question = self.sudo().search(
            [
                ('token', '=', token),
                ('digest', '=', digest),
                ('create_date', '>=', since),
            ]
        )
        question.unlink()
        return bool(question)
