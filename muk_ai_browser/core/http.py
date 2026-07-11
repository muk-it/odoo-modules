from __future__ import annotations

from odoo.http import Request, Session

from odoo.addons.muk_mcp.core.http import resolve_mcp_db
from odoo.addons.muk_web_utils.tools.patch import monkey_patch

BROWSER_PREFIX = '/muk_ai_browser/'


@monkey_patch(Request)
def _get_session_and_dbname(self) -> tuple[Session, str | None]:
    """Resolve the database for browser routes, honouring a ``?db=`` selector.

    The browser extension is a session-less external client, so on a
    multi-database host it selects its database the same way an MCP client does.
    Chains to the muk_mcp resolver, which still handles ``/mcp`` requests.
    """
    session, dbname = _get_session_and_dbname.super(self)
    if not dbname and self.httprequest.path.startswith(BROWSER_PREFIX):
        return session, resolve_mcp_db(self, session)
    return session, dbname
