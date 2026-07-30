from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from lxml import etree, html

# ----------------------------------------------------------
# Extraction Config
# ----------------------------------------------------------

# Dropped wholesale before rendering: non-content, interactive, and
# boilerplate containers (nav/header/footer/aside are readability noise).
_DROP_TAGS = (
    'script',
    'style',
    'noscript',
    'template',
    'svg',
    'iframe',
    'form',
    'input',
    'select',
    'textarea',
    'button',
    'head',
    'nav',
    'header',
    'footer',
    'aside',
)

# Preferred main-content containers, most specific first.
_MAIN_XPATHS = (
    '//main',
    '//article',
    '//*[@role="main"]',
    '//*[@id="content"]',
)
_HEADINGS = {
    'h1': '#',
    'h2': '##',
    'h3': '###',
    'h4': '####',
    'h5': '#####',
    'h6': '######',
}
_SKIP_TAGS = frozenset(_DROP_TAGS)
_WS_RE = re.compile(r'[ \t\r\f\v]+')
_BLANK_RE = re.compile(r'\n{3,}')
_DIGITS_RE = re.compile(r'\d+')

# ``rel`` tokens that mark a link as the page's icon. A scalable icon
# (sizes="any") outranks every pixel size a page can advertise.
_ICON_RELS = frozenset({'icon', 'apple-touch-icon', 'apple-touch-icon-precomposed'})
_ICON_SIZE_ANY = 10_000


# ----------------------------------------------------------
# Public API
# ----------------------------------------------------------


def extract_title(doc: str) -> str | None:
    """Return the collapsed ``<title>`` text of an HTML document, or ``None``."""
    tree = _parse(doc)
    if tree is None:
        return None
    values = tree.xpath('//title/text()')
    if not values:
        return None
    return _WS_RE.sub(' ', values[0]).strip() or None


def extract_icon(doc: str, base_url: str = '') -> str | None:
    """Return the favicon an HTML document declares, absolutised, or ``None``.

    Reads the page's own ``<link rel="icon">`` family rather than assuming
    ``/favicon.ico``, which many sites do not serve. The largest declared
    ``sizes`` wins so a crisp icon is preferred over the legacy 16px one.
    Only ``https`` survives: a page may inline its icon as a ``data:`` URI,
    which would carry tens of kilobytes of base64 into the model's context and
    every stored event, and ``javascript:`` has no business in an ``img`` tag.

    :param doc: the decoded HTML source
    :param base_url: URL the document was fetched from, for relative hrefs
    :return: the icon URL, or ``None`` when the page declares no usable one
    """
    tree = _parse(doc)
    if tree is None:
        return None
    best, best_size = None, -1
    for link in tree.xpath('//link[@rel][@href]'):
        rels = (link.get('rel') or '').lower().split()
        if not any(rel in _ICON_RELS for rel in rels):
            continue
        href = (link.get('href') or '').strip()
        if not href:
            continue
        size = _icon_size(link.get('sizes'))
        if size > best_size:
            best, best_size = href, size
    if not best:
        return None
    url = urljoin(base_url, best)
    return url if urlparse(url).scheme == 'https' else None


def html_to_markdown(doc: str, base_url: str = '') -> str:
    """Convert an HTML document to Markdown, keeping only its main content.

    Non-content and boilerplate (scripts, styles, forms, nav/header/footer/
    aside, comments) are dropped and links/images are absolutised against
    ``base_url`` so the model gets clickable references.

    :return: the rendered Markdown, or ``''`` when the document is unparseable
    """
    root = _clean_main(doc)
    if root is None:
        return ''
    blocks: list[str] = []
    _render_block(root, base_url, blocks)
    markdown = '\n\n'.join(block for block in blocks if block.strip())
    return _BLANK_RE.sub('\n\n', markdown).strip()


def clean_main_html(doc: str) -> str:
    """Return the readability-cleaned main-content HTML of a document.

    :return: the serialised main-content HTML, or ``''`` when unparseable
    """
    root = _clean_main(doc)
    if root is None:
        return ''
    return html.tostring(root, encoding='unicode')


# ----------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------


def _icon_size(sizes: str | None) -> int:
    """Return the pixel edge a ``sizes`` attribute advertises, 0 when absent."""
    value = (sizes or '').strip().lower()
    if value == 'any':
        return _ICON_SIZE_ANY
    return max((int(edge) for edge in _DIGITS_RE.findall(value)), default=0)


def _parse(doc: str) -> html.HtmlElement | None:
    """Parse an HTML string, returning ``None`` when it is empty or invalid."""
    if not doc or not doc.strip():
        return None
    try:
        return html.fromstring(doc)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return None


def _drop(element: html.HtmlElement) -> None:
    """Remove an element from its tree, preserving its tail text."""
    parent = element.getparent()
    if parent is None:
        return
    if element.tail and element.tail.strip():
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or '') + element.tail
        else:
            parent.text = (parent.text or '') + element.tail
    parent.remove(element)


def _pick_main(tree: html.HtmlElement) -> html.HtmlElement:
    """Return the best main-content container in ``tree``."""
    for xpath in _MAIN_XPATHS:
        found = tree.xpath(xpath)
        if found:
            return found[0]
    body = tree.find('.//body')
    return body if body is not None else tree


def _clean_main(doc: str) -> html.HtmlElement | None:
    """Parse, strip boilerplate/comments, and return the main-content element."""
    tree = _parse(doc)
    if tree is None:
        return None
    for comment in tree.iter(etree.Comment):
        _drop(comment)
    for tag in _DROP_TAGS:
        for element in list(tree.iter(tag)):
            _drop(element)
    return _pick_main(tree)


# ----------------------------------------------------------
# Block rendering
# ----------------------------------------------------------


def _render_block(element: html.HtmlElement, base_url: str, out: list[str]) -> None:
    """Render ``element`` and its children into block-level Markdown strings."""
    tag = element.tag if isinstance(element.tag, str) else ''
    if tag in _SKIP_TAGS:
        return
    if tag in _HEADINGS:
        if text := _inline(element, base_url):
            out.append(f'{_HEADINGS[tag]} {text}')
        return
    if tag == 'p':
        if text := _inline(element, base_url):
            out.append(text)
        return
    if tag == 'pre':
        out.append(f'```\n{_plain(element)}\n```')
        return
    if tag == 'blockquote':
        inner: list[str] = []
        _render_children(element, base_url, inner)
        quoted = '\n'.join(f'> {line}' for line in '\n\n'.join(inner).splitlines())
        if quoted.strip():
            out.append(quoted)
        return
    if tag in ('ul', 'ol'):
        out.append(_render_list(element, base_url, ordered=tag == 'ol'))
        return
    if tag == 'hr':
        out.append('---')
        return
    if tag == 'table':
        if table := _render_table(element, base_url):
            out.append(table)
        return
    if tag == 'img':
        if image := _render_image(element, base_url):
            out.append(image)
        return
    _render_children(element, base_url, out)


def _render_children(element: html.HtmlElement, base_url: str, out: list[str]) -> None:
    """Render an element's leading text and every child block."""
    if element.text and element.text.strip():
        out.append(_WS_RE.sub(' ', element.text).strip())
    for child in element:
        _render_block(child, base_url, out)
        if child.tail and child.tail.strip():
            out.append(_WS_RE.sub(' ', child.tail).strip())


def _render_list(element: html.HtmlElement, base_url: str, ordered: bool) -> str:
    """Render a ``<ul>``/``<ol>`` into a Markdown list, indenting nested lists."""
    lines: list[str] = []
    for index, item in enumerate(element.findall('li'), start=1):
        marker = f'{index}.' if ordered else '-'
        lines.append(f'{marker} {_inline(item, base_url)}'.rstrip())
        for sub in item:
            if isinstance(sub.tag, str) and sub.tag in ('ul', 'ol'):
                nested = _render_list(sub, base_url, ordered=sub.tag == 'ol')
                lines.extend(f'    {line}' for line in nested.splitlines())
    return '\n'.join(lines)


def _render_table(element: html.HtmlElement, base_url: str) -> str:
    """Render a ``<table>`` into a GitHub-style pipe table."""
    rows: list[list[str]] = []
    for tr in element.iter('tr'):
        cells = [
            _inline(cell, base_url).replace('|', '\\|').replace('\n', ' ')
            for cell in tr.xpath('./th | ./td')
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return ''
    width = max(len(row) for row in rows)
    rows = [row + [''] * (width - len(row)) for row in rows]
    header, *body = rows
    lines = [
        '| ' + ' | '.join(header) + ' |',
        '| ' + ' | '.join(['---'] * width) + ' |',
    ]
    lines.extend('| ' + ' | '.join(row) + ' |' for row in body)
    return '\n'.join(lines)


def _render_image(element: html.HtmlElement, base_url: str) -> str:
    """Render an ``<img>`` into Markdown image syntax, or ``''`` when src-less."""
    src = element.get('src')
    if not src:
        return ''
    return f'![{element.get("alt") or ""}]({urljoin(base_url, src)})'


# ----------------------------------------------------------
# Inline rendering
# ----------------------------------------------------------


def _inline(element: html.HtmlElement, base_url: str) -> str:
    """Render an element's inline content into a single Markdown string."""
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(_inline_child(child, base_url))
        if child.tail:
            parts.append(child.tail)
    return _WS_RE.sub(' ', ''.join(parts)).strip()


def _inline_child(element: html.HtmlElement, base_url: str) -> str:
    """Render a single inline child element to Markdown."""
    tag = element.tag if isinstance(element.tag, str) else ''
    if tag in _SKIP_TAGS:
        return ''
    if tag == 'br':
        return '\n'
    if tag == 'img':
        return _render_image(element, base_url)
    inner = _inline(element, base_url)
    if tag == 'a':
        href = element.get('href')
        return f'[{inner}]({urljoin(base_url, href)})' if href and inner else inner
    if tag in ('strong', 'b'):
        return f'**{inner}**' if inner else ''
    if tag in ('em', 'i'):
        return f'*{inner}*' if inner else ''
    if tag == 'code':
        return f'`{inner}`' if inner else ''
    return inner


def _plain(element: html.HtmlElement) -> str:
    """Return an element's text content verbatim (for code blocks)."""
    return (element.text_content() or '').strip('\n')
