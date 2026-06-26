from __future__ import annotations

import re

from lxml import etree
from lxml.html.clean import Cleaner

from odoo.tools.mail import html2plaintext

_cleaner = Cleaner(
    scripts=True,
    style=True,
    kill_tags=['script', 'style'],
    remove_unknown_tags=False,
    safe_attrs_only=False,
    page_structure=False,
)


def _extract_main_content(html_content: str) -> str:
    """Return the main content area of an HTML document as an HTML string.

    :return: the ``#wrap`` or ``<main>`` subtree when present, otherwise
        the whole document body or the original input on parse failure
    """
    try:
        doc = etree.HTML(_cleaner.clean_html(html_content))
    except etree.Error:
        return html_content
    body = doc.find('.//body')
    if body is None:
        body = doc
    main = body.find('.//*[@id="wrap"]')
    if main is None:
        main = body.find('.//main')
    if main is None:
        main = body
    return etree.tostring(main, encoding='unicode', method='html')


def html_to_markdown(html_content: str | bytes | None, base_url: str = '') -> str:
    """Convert website HTML into clean, collapsed plain-text markdown."""
    if not html_content:
        return ''
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='replace')
    content = _extract_main_content(html_content)
    text = html2plaintext(content)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def estimate_tokens(text: str | None) -> int:
    """Estimate the number of LLM tokens in ``text`` from its word count."""
    if not text:
        return 0
    words = len(text.split())
    return int(words * 1.3)


def build_content_signal(policy: str) -> str:
    """Map a content-signal policy to its ``Content-Signal`` header value."""
    signals = {
        'all': 'ai-train=yes, search=yes, ai-input=yes',
        'search_input': 'ai-train=no, search=yes, ai-input=yes',
        'input_only': 'ai-train=no, search=no, ai-input=yes',
        'none': 'ai-train=no, search=no, ai-input=no',
    }
    return signals.get(policy, signals['all'])
