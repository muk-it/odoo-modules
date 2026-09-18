from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlparse

SourceExtractor = Callable[[dict, object], list[dict]]

MAX_RECORD_SOURCES_PER_CALL = 20
MAX_WEB_SEARCH_SOURCES_PER_CALL = 10

UNSET_MODULE_ICON = '/base/static/description/icon.png'

# ----------------------------------------------------------
# Registry
# ----------------------------------------------------------

SOURCE_EXTRACTORS: dict[str, SourceExtractor] = {}


def source_extractor(*tool_names: str) -> Callable[[SourceExtractor], SourceExtractor]:
    """Register a function that maps a tool result to source descriptors.

    Only tools whose results should be citable (a specific web page, a
    specific record) opt in — bulk discovery tools (``search_read``) and
    client-executed tools stay out so the sources rail is not flooded.
    """

    def register(func: SourceExtractor) -> SourceExtractor:
        for name in tool_names:
            SOURCE_EXTRACTORS[name] = func
        return func

    return register


def extract_sources(name: str, arguments: dict | None, result: object) -> list[dict]:
    """Return the source descriptors a tool call contributed, or an empty list.

    ``result`` is whatever the dispatcher recorded — a structured object or,
    as tool outputs are transported, its JSON-serialized string; the string
    form is parsed back before extraction. Never raises: a misbehaving
    extractor yields no sources rather than breaking the tool round.
    """
    extractor = SOURCE_EXTRACTORS.get(name)
    if not extractor:
        return []
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (ValueError, TypeError):
            return []
    try:
        return extractor(arguments or {}, result) or []
    except Exception:
        return []


# ----------------------------------------------------------
# Extractors
# ----------------------------------------------------------


def web_domain(url: str) -> str:
    """Return the host of ``url`` without a leading ``www.``, '' when it has none."""
    domain = urlparse(url).hostname or ''
    return domain[4:] if domain.startswith('www.') else domain


def _web_source(url: str, title: str | None, icon: str | None) -> dict:
    """Build a web source descriptor keyed by URL, so a page cited twice merges."""
    domain = web_domain(url)
    source = {
        'id': f'web:{url}',
        'type': 'web',
        'url': url,
        'title': title or domain or url,
        'domain': domain,
    }
    if icon:
        source['icon'] = icon
    return source


@source_extractor('web_fetch')
def _web_fetch_sources(arguments: dict, result: object) -> list[dict]:
    """Turn a ``web_fetch`` descriptor into a single web source (sans content)."""
    if not isinstance(result, dict) or result.get('error'):
        return []
    if not (url := result.get('url')):
        return []
    return [_web_source(url, result.get('title'), result.get('icon'))]


@source_extractor('web_search')
def _web_search_sources(arguments: dict, result: object) -> list[dict]:
    """Turn ``web_search`` hits into capped web sources sharing ``web_fetch``'s ids."""
    if not isinstance(result, dict) or result.get('error'):
        return []
    hits = [
        hit
        for hit in result.get('results') or []
        if isinstance(hit, dict) and hit.get('url')
    ]
    return [
        _web_source(hit['url'], hit.get('title'), hit.get('icon'))
        for hit in hits[:MAX_WEB_SEARCH_SOURCES_PER_CALL]
    ]


def _record_source(model: str, row: object) -> dict | None:
    """Build a record source descriptor from a read row, or ``None`` if it has no id."""
    if not isinstance(row, dict) or (rid := row.get('id')) is None:
        return None
    return {
        'id': f'record:{model},{rid}',
        'type': 'record',
        'res_model': model,
        'res_id': rid,
        'display_name': row.get('display_name') or row.get('name') or f'{model},{rid}',
        'href': f'/odoo/{model}/{rid}',
    }


def _rows_to_record_sources(
    model: str, rows: list, limit: int | None = None
) -> list[dict]:
    """Map read rows to record sources, stopping once ``limit`` are collected."""
    sources = []
    for row in rows:
        if (source := _record_source(model, row)) is None:
            continue
        sources.append(source)
        if limit is not None and len(sources) >= limit:
            break
    return sources


@source_extractor('read_records', 'search_read')
def _record_read_sources(arguments: dict, result: object) -> list[dict]:
    """Turn read rows (``read_records``/``search_read``) into capped record sources."""
    model = arguments.get('model')
    if not model or not isinstance(result, list):
        return []
    return _rows_to_record_sources(model, result, limit=MAX_RECORD_SOURCES_PER_CALL)


# ----------------------------------------------------------
# App icons
# ----------------------------------------------------------


def web_icon_url(web_icon: str) -> str:
    """Turn a menu ``web_icon`` ("module,path") into a served URL, '' if unusable.

    Only the two-segment form names a file; Studio's built icons use the same
    attribute for a ``class,colour,background`` triplet, which addresses no
    image. ``UNSET_MODULE_ICON`` is refused too: Odoo serves that one file for
    every module shipping no icon of its own, so it means "none" rather than
    the Base app.
    """
    segments = (web_icon or '').split(',')
    if len(segments) != 2 or not all(segment.strip() for segment in segments):
        return ''
    url = f'/{segments[0].strip()}/{segments[1].strip()}'
    return '' if url == UNSET_MODULE_ICON else url
