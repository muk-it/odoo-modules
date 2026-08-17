from __future__ import annotations

import re
from urllib.parse import urlsplit

from lxml import etree, html

TAG_SOURCES = (
    ('script', 'src'),
    ('iframe', 'src'),
    ('img', 'src'),
    ('link', 'href'),
    ('source', 'src'),
    ('embed', 'src'),
    ('object', 'data'),
)

BLOCKED_SOURCE_ATTRIBUTE = 'data-nocookie-src'

STORAGE_CALL = re.compile(
    r'\b(localStorage|sessionStorage)\s*(?:\.setItem\(\s*|\[\s*)'
    r'[\'"]([\w.:@-]{1,64})[\'"]'
)

COOKIE_ASSIGNMENT = re.compile(r'document\.cookie\s*=\s*[\'"]([\w.-]{1,64})\s*=')

STORAGE_KIND = {'localStorage': 'local', 'sessionStorage': 'session'}


def normalise_host(host: str) -> str:
    """Return a host without its ``www.`` prefix, lowercased."""
    return (host or '').lower().removeprefix('www.')


def extract_hosts(markup: str, own_hosts: set[str]) -> set[str]:
    """Return the third-party hosts a page loads from.

    Reads the blocked source attribute as well as the live one, so a page
    fetched while something was still gated reports the host it would have
    called rather than ``about:blank``.
    """
    try:
        root = html.fromstring(markup)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return set()
    found = set()
    references = [
        element.get(attribute)
        for tag, attribute in TAG_SOURCES
        for element in root.iter(tag)
    ]
    references += [
        element.get(BLOCKED_SOURCE_ATTRIBUTE)
        for element in root.xpath(f'//*[@{BLOCKED_SOURCE_ATTRIBUTE}]')
    ]
    for reference in references:
        reference = (reference or '').strip()
        if reference.startswith('//'):
            reference = f'https:{reference}'
        if not reference.lower().startswith(('http://', 'https://')):
            continue
        host = normalise_host(urlsplit(reference).hostname or '')
        if host and host not in own_hosts:
            found.add(host)
    return found


def extract_storage_keys(markup: str) -> set[tuple[str, str]]:
    """Return the storage keys the page's own scripts write.

    A server-side scan cannot read the browser's storage, so the next best
    evidence is the code that fills it. Only inline scripts are covered, which
    is why the review list stays open to keys nobody found this way.

    :return: pairs of storage type and key name
    """
    return {
        (STORAGE_KIND[kind], name) for kind, name in STORAGE_CALL.findall(markup or '')
    }


def extract_cookie_names(markup: str) -> set[str]:
    """Return the cookie names the page's own scripts set."""
    return set(COOKIE_ASSIGNMENT.findall(markup or ''))


def extract_keys(markup: str, own_hosts: set[str], url: str) -> list[dict]:
    """Return everything one fetched page reveals, ready to be filed.

    :param own_hosts: the site's own hosts, which are never third parties
    :param url: the page the markup came from, kept as the review hint
    """
    keys = [
        {'name': host, 'type': 'host', 'url': url}
        for host in extract_hosts(markup, own_hosts)
    ]
    keys += [
        {'name': name, 'type': storage_type, 'url': url}
        for storage_type, name in extract_storage_keys(markup)
    ]
    keys += [
        {'name': name, 'type': 'http', 'url': url}
        for name in extract_cookie_names(markup)
    ]
    return keys
