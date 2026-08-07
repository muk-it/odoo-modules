from __future__ import annotations

import re

from odoo import models

SESSION_CHANNEL_RE = re.compile(r'^muk_ai\.session_(\d+)$')


class IrWebsocket(models.AbstractModel):
    """Let a client follow the chats it is allowed to read."""

    _inherit = 'ir.websocket'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _build_bus_channel_list(self, channels: list) -> list:
        """Subscribe the caller to the chats they asked for and may read.

        A client may only name string channels, which never collide with the
        record channels a session publishes on, so the subscription is worth
        exactly what this method grants: the search applies the record rules,
        and a chat the caller cannot read is simply never added.
        """
        channels = list(channels)
        session_ids = []
        for channel in list(channels):
            match = isinstance(channel, str) and SESSION_CHANNEL_RE.match(channel)
            if match:
                channels.remove(channel)
                session_ids.append(int(match.group(1)))
        sessions = self.env['muk_ai.session']
        if session_ids and sessions.has_access('read'):
            channels.extend(sessions.search([('id', 'in', session_ids)]))
        return super()._build_bus_channel_list(channels)
