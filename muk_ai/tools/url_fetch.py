from __future__ import annotations

import ipaddress
import json
import re
import socket
from typing import NamedTuple
from urllib.parse import urljoin, urlparse

import urllib3

from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.translate import LazyTranslate

from .parser import clean_main_html, extract_icon, extract_title, html_to_markdown

_lt = LazyTranslate('muk_ai')

# ----------------------------------------------------------
# Fetch Limits
# ----------------------------------------------------------

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 25
CHUNK_SIZE = 64 * 1024
URL_FETCH_MAX_BYTES = 16 * 1024 * 1024
MAX_REDIRECTS = 5

WEB_FETCH_MAX_CHARS = 100_000

USER_AGENT = 'Mozilla/5.0 (compatible; MuK-AI/1.0; +https://www.mukit.at)'
ACCEPT = (
    'text/markdown,text/html;q=0.9,application/xhtml+xml;q=0.8,'
    'text/plain;q=0.7,application/json;q=0.7,*/*;q=0.5'
)

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_HTML_SNIFF_RE = re.compile(rb'<\s*(?:!doctype\s+html|html|head|body)\b', re.IGNORECASE)
_GITHUB_BLOB_RE = re.compile(
    r'^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$', re.IGNORECASE
)

# ----------------------------------------------------------
# SSRF Guard
# ----------------------------------------------------------

UNSAFE_IP_ATTRS = (
    'is_private',
    'is_loopback',
    'is_link_local',
    'is_reserved',
    'is_multicast',
    'is_unspecified',
)


class FetchResult(NamedTuple):
    """A fetched page: its final URL, raw body, and decoded metadata."""

    url: str
    body: bytes
    content_type: str
    charset: str | None


def _normalize_url(url: str) -> str:
    """Upgrade ``http`` to ``https`` and rewrite GitHub blob URLs to raw."""
    url = (url or '').strip()
    if url.startswith('http://'):
        url = 'https://' + url[len('http://') :]
    if match := _GITHUB_BLOB_RE.match(url):
        owner, repo, rest = match.groups()
        url = f'https://raw.githubusercontent.com/{owner}/{repo}/{rest}'
    return url


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


def _charset(content_type: str) -> str | None:
    """Return the ``charset`` from a Content-Type header, or ``None``."""
    for part in content_type.split(';')[1:]:
        key, _, value = part.strip().partition('=')
        if key.strip().lower() == 'charset':
            return value.strip().strip('"\'') or None
    return None


def _read_body(response: urllib3.HTTPResponse, url: str) -> bytes:
    """Stream a response body, enforcing the size cap.

    :raise UserError: when the body exceeds ``URL_FETCH_MAX_BYTES``
    """
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


def fetch_url(url: str) -> FetchResult:
    """Fetch an ``https://`` URL, following redirects with SSRF guards.

    Every redirect hop is re-validated against the SSRF guard and pinned to
    its resolved IP, so a public URL cannot bounce the fetch to an internal
    address. ``http`` URLs are upgraded to ``https`` and GitHub blob URLs are
    rewritten to their raw endpoint.

    :return: the fetched page with its final URL and decoded metadata
    :raise UserError: on validation failure, an HTTP error status, a missing
        redirect target, too many redirects, or a body over the size cap
    """
    current = _normalize_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        host, resolved = _validate_url(current)
        parsed = urlparse(current)
        path = parsed.path or '/'
        if parsed.query:
            path = f'{path}?{parsed.query}'
        pool = urllib3.HTTPSConnectionPool(
            host=resolved[0],
            port=parsed.port or 443,
            assert_hostname=host,
            server_hostname=host,
            timeout=urllib3.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
            retries=False,
        )
        try:
            response = pool.urlopen(
                'GET',
                path,
                headers={
                    'Host': host,
                    'User-Agent': USER_AGENT,
                    'Accept': ACCEPT,
                    'Accept-Language': 'en-US,en;q=0.9',
                },
                preload_content=False,
                redirect=False,
            )
            try:
                if response.status in _REDIRECT_STATUSES:
                    if not (location := response.headers.get('Location')):
                        raise UserError(
                            _lt('@url: redirect from %s had no Location.', current)
                        )
                    current = _normalize_url(urljoin(current, location))
                    continue
                if response.status >= 400:
                    raise UserError(
                        _lt(
                            '@url: HTTP %(status)s for %(url)s.',
                            status=response.status,
                            url=current,
                        )
                    )
                body = _read_body(response, current)
                raw_type = response.headers.get('Content-Type', '') or ''
                return FetchResult(
                    url=current,
                    body=body,
                    content_type=raw_type.split(';')[0].strip().lower(),
                    charset=_charset(raw_type),
                )
            finally:
                response.release_conn()
        finally:
            pool.close()
    raise UserError(_lt('@url: too many redirects for %s.', url))


def _is_html(result: FetchResult) -> bool:
    """Return whether a fetched payload should be rendered as HTML."""
    mime = result.content_type
    return 'html' in mime or (
        not mime and bool(_HTML_SNIFF_RE.search(result.body[:1024]))
    )


def page_icon(result: FetchResult) -> str | None:
    """Return the favicon a fetched HTML page declares, or ``None``.

    Resolved from the markup the fetch already retrieved, so a cited page
    carries its real icon instead of the client guessing ``/favicon.ico``
    and falling back to a glyph whenever that guess misses.
    """
    if not _is_html(result):
        return None
    text = result.body.decode(result.charset or 'utf-8', errors='replace')
    return extract_icon(text, result.url)


def render_content(
    result: FetchResult, mode: str = 'markdown'
) -> tuple[str | None, str]:
    """Render a fetched page to model-readable text and extract its title.

    Modes: ``markdown`` (default) converts HTML to Markdown keeping only the
    main content; ``text`` returns the main content as plain text; ``html``
    returns the decoded source untouched. Non-HTML payloads ignore the mode —
    JSON is pretty-printed, other text is returned as-is, and binary payloads
    return a short placeholder — except ``html`` which always returns source.

    :return: the page title (or ``None``) and its rendered content
    """
    text = result.body.decode(result.charset or 'utf-8', errors='replace')
    mime = result.content_type
    html_like = _is_html(result)
    if mode == 'html':
        return (extract_title(text) if html_like else None), text
    if html_like:
        title = extract_title(text)
        if mode == 'text':
            return title, (
                html2plaintext(clean_main_html(text) or text) or text.strip()
            )
        markdown = html_to_markdown(text, result.url)
        return title, (markdown or html2plaintext(text) or text.strip())
    if 'json' in mime:
        return None, _pretty_json(text)
    if not mime or mime.startswith('text/') or 'xml' in mime or 'javascript' in mime:
        return None, text.strip()
    return None, f'[{mime} content — {len(result.body)} bytes, not rendered as text]'


def _pretty_json(text: str) -> str:
    """Pretty-print a JSON string, returning it unchanged when invalid."""
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return text.strip()
