from __future__ import annotations

from dataclasses import dataclass

MCP_VERSION_2025_06_18 = '2025-06-18'
MCP_VERSION_2025_11_25 = '2025-11-25'
MCP_VERSION_2026_07_28 = '2026-07-28'

MCP_DEFAULT_VERSION = MCP_VERSION_2025_06_18

MCP_PROTOCOL_VERSION_HEADER = 'MCP-Protocol-Version'

META_PROTOCOL_VERSION = 'io.modelcontextprotocol/protocolVersion'
META_CLIENT_INFO = 'io.modelcontextprotocol/clientInfo'
META_CLIENT_CAPABILITIES = 'io.modelcontextprotocol/clientCapabilities'


@dataclass(frozen=True)
class ProtocolProfile:
    """Behaviour flags describing a single MCP protocol revision."""

    version: str
    stateless: bool


_PROFILES = {
    MCP_VERSION_2025_06_18: ProtocolProfile(
        version=MCP_VERSION_2025_06_18,
        stateless=False,
    ),
    MCP_VERSION_2025_11_25: ProtocolProfile(
        version=MCP_VERSION_2025_11_25,
        stateless=False,
    ),
    MCP_VERSION_2026_07_28: ProtocolProfile(
        version=MCP_VERSION_2026_07_28,
        stateless=True,
    ),
}

MCP_SUPPORTED_VERSIONS = (
    MCP_VERSION_2026_07_28,
    MCP_VERSION_2025_11_25,
    MCP_VERSION_2025_06_18,
)

MCP_HANDSHAKE_VERSIONS = tuple(
    candidate
    for candidate in MCP_SUPPORTED_VERSIONS
    if not _PROFILES[candidate].stateless
)

MCP_LATEST_HANDSHAKE_VERSION = MCP_HANDSHAKE_VERSIONS[0]


def is_supported(version: str | None) -> bool:
    """Report whether ``version`` is a revision this server serves."""
    return version in MCP_SUPPORTED_VERSIONS


def negotiate_handshake(requested: str | None) -> str:
    """Return the revision to negotiate on an ``initialize`` handshake.

    Only the session-based revisions can be negotiated this way: the stateless
    one has no handshake, so answering it here would hand the client a session
    for a revision that forbids sessions. A client naming it -- or naming a
    revision we do not serve -- is answered the newest session-based one, as the
    transport asks a server to offer its latest supported revision.
    """
    if is_supported(requested) and not get_profile(requested).stateless:
        return requested
    return MCP_LATEST_HANDSHAKE_VERSION


def get_profile(version: str | None) -> ProtocolProfile:
    """Return the behaviour profile for ``version``, defaulting when unknown."""
    return _PROFILES.get(version or '', _PROFILES[MCP_DEFAULT_VERSION])
