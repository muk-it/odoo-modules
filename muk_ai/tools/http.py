from __future__ import annotations

import functools
import ssl

import requests
from urllib3.exceptions import ProtocolError, SSLError
from urllib3.util.retry import Retry


class ResetConnectionRetry(Retry):
    """Retry policy that treats a connection the peer reset as never reached."""

    def _is_connection_error(self, err: Exception) -> bool:
        """Count a reset, closed or TLS-cut pooled connection as a connection error.

        A keep-alive connection that a NAT or the server dropped fails with
        ``Connection aborted``, a TLS EOF or a bad record MAC alert before any
        answer came back, so the request is replayed like a failed connect.
        """
        return (
            super()._is_connection_error(err)
            or (
                isinstance(err, ProtocolError)
                and len(err.args) > 1
                and isinstance(err.args[1], (ConnectionResetError, BrokenPipeError))
            )
            or (
                isinstance(err, SSLError)
                and bool(err.args)
                and (
                    isinstance(err.args[0], ssl.SSLEOFError)
                    or getattr(err.args[0], 'reason', None)
                    == 'SSLV3_ALERT_BAD_RECORD_MAC'
                )
            )
        )


@functools.lru_cache(maxsize=1)
def http_session() -> requests.Session:
    """Return the process-wide HTTP session pooling keep-alive connections.

    Built lazily inside the worker; retries re-establish dropped connections
    and never replay a request whose answer timed out.
    """
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_maxsize=32,
        max_retries=ResetConnectionRetry(
            total=2,
            connect=2,
            read=False,
            status=0,
            redirect=False,
            other=0,
            allowed_methods=None,
        ),
    )
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session
