from __future__ import annotations

import logging
from functools import partial

from odoo import SUPERUSER_ID, api, models
from odoo.http import Response, request
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    """Run AI turns queued during a request once its response was sent."""

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _run_queued_turns(dbname: str, session_ids: tuple[int, ...]) -> None:
        """Run the turns queued during a request in a cursor of their own.

        :param dbname: database the queued sessions belong to
        :param session_ids: sessions to hand to the worker, in queue order
        """
        try:
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['muk_ai.session']._dispatch_in_slot(session_ids)
        except Exception:  # noqa: BLE001 — never surface after the response was sent
            _logger.exception('Inline AI dispatch failed for sessions %s', session_ids)

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @classmethod
    def _post_dispatch(cls, response: Response) -> None:
        """Hand queued AI turns to the response close callback."""
        super()._post_dispatch(response)
        session_ids = request.__dict__.pop('muk_ai_dispatch_ids', ())
        if session_ids and not response.direct_passthrough:
            response.call_on_close(
                partial(cls._run_queued_turns, request.db, session_ids)
            )
