from __future__ import annotations

from odoo.http import Request, Session, db_filter
from odoo.tools import config

from odoo.addons.muk_web_utils.tools.patch import monkey_patch


def resolve_mcp_db(request: Request, session: Session) -> str | None:
    """Resolve an MCP request's database from a ``?db=`` selector."""
    host = request.httprequest.environ['HTTP_HOST']
    db_param = config.get('mcp_db_param', 'db')
    database = (request.httprequest.args.get(db_param) or '').strip()
    if database and db_filter([database], host=host):
        session.can_save = False
        session.db = database
        return database
    return None


@monkey_patch(Request)
def _get_session_and_dbname(self) -> tuple[Session, str | None]:
    """Resolve the database for ``/mcp`` requests, honouring a ``?db=`` selector."""
    if (path := self.httprequest.path) == '/mcp' or path.startswith('/mcp/'):
        session, dbname = _get_session_and_dbname.super(self)
        return session, dbname or resolve_mcp_db(self, session)
    return _get_session_and_dbname.super(self)
