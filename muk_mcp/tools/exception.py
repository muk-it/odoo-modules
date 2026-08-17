from odoo.exceptions import AccessError


class MCPResourceNotFound(Exception):
    """Raised when ``resources/read`` cannot resolve the requested URI."""


class MCPScopeDenied(AccessError):
    pass
