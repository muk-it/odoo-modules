from __future__ import annotations

from odoo.exceptions import AccessError


class MCPResourceNotFound(Exception):
    """Raised when ``resources/read`` cannot resolve the requested URI."""


class MCPScopeDenied(AccessError):
    """Raised when a request is denied by the API key's scope."""
