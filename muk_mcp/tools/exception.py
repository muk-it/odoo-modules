from __future__ import annotations

from typing import Any

from odoo.exceptions import AccessError


class MCPResourceNotFound(Exception):
    """Raised when ``resources/read`` cannot resolve the requested URI."""


class MCPScopeDenied(AccessError):
    """Raised when a request is denied by the API key's scope."""


class MCPInputRequired(AccessError):
    """Raised when a call needs the input of the user before it may run."""

    def __init__(self, message: str, requests: dict[str, Any], state: str) -> None:
        """Keep the requests for the client and the state it echoes on the retry."""
        super().__init__(message)
        self.requests = requests
        self.state = state


class MCPCapabilityRequired(AccessError):
    """Raised when a call needs a capability the client did not declare."""

    def __init__(self, message: str, capabilities: dict[str, Any]) -> None:
        """Keep the capabilities the client has to declare."""
        super().__init__(message)
        self.capabilities = capabilities
