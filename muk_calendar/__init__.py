from __future__ import annotations

from odoo.api import Environment

from . import controllers
from . import models


def _uninstall_hook(env: Environment) -> None:
    """Delete the automations that keep record calendars in sync."""
    env['base.automation'].with_context(active_test=False).search(
        [('action_server_ids.state', '=', 'calendar_sync')]
    ).unlink()
