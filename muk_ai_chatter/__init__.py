from __future__ import annotations

from odoo.api import Environment

from . import models


def _post_init_hook(env: Environment) -> None:
    """Give the agents that predate this module their stand-in contact."""
    env['muk_ai.agent'].with_context(active_test=False).search(
        [('partner_id', '=', False)]
    )._provision_partners()
