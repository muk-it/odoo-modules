from __future__ import annotations

import functools

import requests


@functools.lru_cache(maxsize=1)
def http_session() -> requests.Session:
    """Return the process-wide HTTP session pooling keep-alive connections.

    Cached rather than eager so the pool is built inside a worker and no
    socket ever crosses ``fork()``. Retries are connect-only: a dead pooled
    socket is re-established, but a request that already reached the server is
    never replayed.
    """
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_maxsize=32,
        max_retries=requests.adapters.Retry(
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
