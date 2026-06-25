from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import urllib3

from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate('muk_ai')

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 25
CHUNK_SIZE = 64 * 1024
URL_FETCH_MAX_BYTES = 16 * 1024 * 1024
UNSAFE_IP_ATTRS = (
    'is_private',
    'is_loopback',
    'is_link_local',
    'is_reserved',
    'is_multicast',
    'is_unspecified',
)


def _validate_url(url: str) -> tuple[str, list[str]]:
    """Validate an ``@url`` target and resolve it to publicly routable addresses.

    :return: the hostname and its resolved IP addresses
    :raise UserError: when the scheme/host is invalid, DNS fails, or any
        resolved address is not publicly routable (SSRF guard)
    """
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise UserError(_lt('@url: only accepts https:// URLs.'))
    if not (host := parsed.hostname):
        raise UserError(_lt('@url: missing hostname.'))
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UserError(_lt('@url: DNS lookup failed for %s: %s', host, exc)) from exc
    resolved = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(getattr(ip, attr) for attr in UNSAFE_IP_ATTRS):
            raise UserError(
                _lt(
                    '@url: refusing to fetch %s — %s is not publicly routable.',
                    host,
                    ip,
                )
            )
        resolved.append(str(ip))
    if not resolved:
        raise UserError(
            _lt(
                '@url: DNS lookup returned no addresses for %s.',
                host,
            )
        )
    return host, resolved


def fetch_url(url: str) -> bytes:
    """Fetch an ``https://`` URL with SSRF guards and a response size cap.

    :return: the raw response body
    :raise UserError: on validation failure, an HTTP error status, or when
        the response exceeds the size cap
    """
    host, resolved = _validate_url(url)
    parsed = urlparse(url)
    path = parsed.path or '/'
    if parsed.query:
        path = f'{path}?{parsed.query}'
    pool = urllib3.HTTPSConnectionPool(
        host=resolved[0],
        port=parsed.port or 443,
        assert_hostname=host,
        timeout=urllib3.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
        retries=False,
        conn_kw={'server_hostname': host},
    )
    try:
        response = pool.urlopen(
            'GET',
            path,
            headers={'Host': host},
            preload_content=False,
            redirect=False,
        )
        try:
            if response.status >= 400:
                raise UserError(
                    _lt(
                        '@url: HTTP %(status)s for %(url)s.',
                        status=response.status,
                        url=url,
                    )
                )
            chunks, total = [], 0
            for chunk in response.stream(CHUNK_SIZE):
                chunks.append(chunk)
                total += len(chunk)
                if total > URL_FETCH_MAX_BYTES:
                    raise UserError(
                        _lt(
                            '@url: response from %s exceeds the %s MiB cap.',
                            url,
                            URL_FETCH_MAX_BYTES // (1024 * 1024),
                        )
                    )
            return b''.join(chunks)
        finally:
            response.release_conn()
    finally:
        pool.close()
