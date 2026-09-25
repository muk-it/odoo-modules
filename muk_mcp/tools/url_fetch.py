from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import urllib3

from odoo import _
from odoo.exceptions import UserError

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 25
CHUNK_SIZE = 64 * 1024
MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

UNSAFE_IP_ATTRS = (
    'is_private',
    'is_loopback',
    'is_link_local',
    'is_reserved',
    'is_multicast',
    'is_unspecified',
)


def _normalize_url(url: str) -> str:
    """Strip the URL and upgrade ``http`` to ``https``."""
    url = (url or '').strip()
    if url.startswith('http://'):
        url = 'https://' + url[len('http://') :]
    return url


def _resolve_public_host(url: str) -> tuple[str, str]:
    """Resolve the URL's host and ensure every address is publicly routable.

    :return: the hostname and the address to pin the connection to
    :raise UserError: when the scheme or host is invalid, DNS fails, or any
        resolved address is private, loopback, link-local or otherwise
        internal (SSRF guard)
    """
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise UserError(_('Only https:// URLs can be downloaded: %s', url))
    if not (host := parsed.hostname):
        raise UserError(_('The URL %s has no hostname.', url))
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        raise UserError(
            _('DNS lookup failed for %(host)s: %(error)s', host=host, error=error),
        ) from error
    addresses = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if any(getattr(address, attr) for attr in UNSAFE_IP_ATTRS):
            raise UserError(
                _(
                    'Refusing to download from %(host)s: %(address)s is not '
                    'publicly routable.',
                    host=host,
                    address=address,
                ),
            )
        addresses.append(str(address))
    if not addresses:
        raise UserError(_('DNS lookup returned no addresses for %s.', host))
    return host, addresses[0]


def _read_response(
    response: urllib3.HTTPResponse,
    url: str,
    max_bytes: int,
) -> tuple[str | None, bytes, str]:
    """Return the redirect location, or the body and content type of a response.

    The body is streamed and the read stops as soon as it exceeds ``max_bytes``.

    :return: the redirect location (``None`` unless redirected), the body, and
        its lowercased content type without parameters
    :raise UserError: when a redirect has no location, the status is an HTTP
        error, or the body exceeds ``max_bytes``
    """
    try:
        if response.status in REDIRECT_STATUSES:
            if not (location := response.headers.get('Location')):
                raise UserError(_('The redirect from %s has no location.', url))
            return location, b'', ''
        if response.status >= 400:
            raise UserError(
                _(
                    'Downloading %(url)s failed with HTTP %(status)s.',
                    url=url,
                    status=response.status,
                ),
            )
        chunks, total = [], 0
        for chunk in response.stream(CHUNK_SIZE):
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise UserError(
                    _(
                        'The file at %(url)s exceeds the limit of %(limit)s bytes.',
                        url=url,
                        limit=max_bytes,
                    ),
                )
        content_type = response.headers.get('Content-Type') or ''
        return None, b''.join(chunks), content_type.split(';')[0].strip().lower()
    finally:
        response.release_conn()


def fetch_url(url: str, max_bytes: int = MAX_BYTES) -> tuple[bytes, str]:
    """Download a public ``https://`` URL, following redirects with SSRF guards.

    Every hop is re-validated and pinned to the checked address, so neither a
    redirect nor a DNS rebind can point the download at an internal host.

    :return: the body and its lowercased content type without parameters
    :raise UserError: on validation failure, a connection error, an HTTP error
        status, too many redirects, or a body over ``max_bytes``
    """
    current = _normalize_url(url)
    for _hop in range(MAX_REDIRECTS + 1):
        host, address = _resolve_public_host(current)
        parsed = urlparse(current)
        path = parsed.path or '/'
        if parsed.query:
            path = f'{path}?{parsed.query}'
        pool = urllib3.HTTPSConnectionPool(
            host=address,
            port=parsed.port or 443,
            assert_hostname=host,
            server_hostname=host,
            timeout=urllib3.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
            retries=False,
        )
        with pool:
            try:
                location, body, content_type = _read_response(
                    pool.urlopen(
                        'GET',
                        path,
                        headers={'Host': host},
                        preload_content=False,
                        redirect=False,
                    ),
                    current,
                    max_bytes,
                )
            except urllib3.exceptions.HTTPError as error:
                raise UserError(
                    _(
                        'Downloading %(url)s failed: %(error)s',
                        url=current,
                        error=error,
                    ),
                ) from error
        if location is None:
            return body, content_type
        current = _normalize_url(urljoin(current, location))
    raise UserError(_('Too many redirects for %s.', url))
