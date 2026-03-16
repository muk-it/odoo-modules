import re

from lxml import etree

from odoo.tools.mail import html2plaintext


def _extract_main_content(html_content):
    try:
        doc = etree.HTML(html_content)
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


def html_to_markdown(html_content, base_url=''):
    if not html_content:
        return ''
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='replace')
    content = _extract_main_content(html_content)
    text = html2plaintext(content)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def estimate_tokens(text):
    if not text:
        return 0
    words = len(text.split())
    return int(words * 1.3)


def build_content_signal(policy):
    signals = {
        'all': 'ai-train=yes, search=yes, ai-input=yes',
        'search_input': 'ai-train=no, search=yes, ai-input=yes',
        'input_only': 'ai-train=no, search=no, ai-input=yes',
        'none': 'ai-train=no, search=no, ai-input=no',
    }
    return signals.get(policy, signals['all'])
