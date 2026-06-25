from __future__ import annotations

from odoo.exceptions import AccessError


class MCPScopeDenied(AccessError):
    """Raised when a request is denied by the API key's scope."""
