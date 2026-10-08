from __future__ import annotations

import functools

import requests
from urllib3.exceptions import ProtocolError
from urllib3.util.retry import Retry


class ResetConnectionRetry(Retry):
    """Retry policy that treats a connection the peer reset as never reached."""

    def _is_connection_error(self, err: Exception) -> bool:
        """Count a reset or closed pooled connection as a connection error.

        A keep-alive connection that a NAT or the server dropped while idle
        fails on the next request with ``Connection aborted``; the request
        never got an answer, so it is replayed like a failed connect.
        """
        return super()._is_connection_error(err) or (
            isinstance(err, ProtocolError)
            and len(err.args) > 1
            and isinstance(err.args[1], (ConnectionResetError, BrokenPipeError))
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
