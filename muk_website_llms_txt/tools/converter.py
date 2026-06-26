import json
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


def _extract_main_content(html_content):
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


def html_to_markdown(html_content, base_url=''):
    if not html_content:
        return ''
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='replace')
    content = _extract_main_content(html_content)
    text = html2plaintext(content)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_jsonld(html_content):
    objects = []
    if not html_content:
        return objects
    try:
        doc = etree.HTML(html_content)
    except (etree.Error, ValueError):
        return objects
    if doc is None:
        return objects
    for script in doc.iterfind('.//script'):
        if (script.get('type') or '').lower() != 'application/ld+json':
            continue
        if not script.text:
            continue
        try:
            parsed = json.loads(script.text)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, list):
            objects.extend(parsed)
        else:
            objects.append(parsed)
    return objects


def extract_metadata(html_content):
    meta = {}
    if not html_content:
        return meta
    try:
        doc = etree.HTML(html_content)
    except (etree.Error, ValueError):
        return meta
    if doc is None:
        return meta
    title = doc.find('.//title')
    if title is not None and title.text:
        meta['title'] = title.text.strip()
    for el in doc.iterfind('.//meta'):
        key = (el.get('name') or el.get('property') or '').lower()
        content = (el.get('content') or '').strip()
        if not content:
            continue
        if key == 'og:title':
            meta['title'] = content
        elif key in ('description', 'og:description') and 'description' not in meta:
            meta['description'] = content
        elif key == 'og:image' and 'image' not in meta:
            meta['image'] = content
    return meta


def _yaml_quote(value):
    collapsed = ' '.join(value.split())
    escaped = collapsed.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _build_frontmatter(meta):
    keys = [key for key in ('title', 'description', 'image') if meta.get(key)]
    if not keys:
        return ''
    lines = ['---']
    lines += [f'{key}: {_yaml_quote(meta[key])}' for key in keys]
    lines.append('---')
    return '\n'.join(lines)


def _iter_products(objects):
    products = []

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if node.get('@graph'):
                walk(node['@graph'])
            node_type = node.get('@type')
            types = node_type if isinstance(node_type, list) else [node_type]
            if 'Product' in types:
                products.append(node)

    for obj in objects:
        walk(obj)
    return products


def _product_summary(objects):
    products = _iter_products(objects)
    if not products:
        return ''
    product = products[0]
    parts = []
    if product.get('name'):
        parts.append(str(product['name']))
    offers = product.get('offers')
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if isinstance(offers, dict):
        price = offers.get('price')
        if price is not None:
            parts.append(f'{price} {offers.get("priceCurrency", "")}'.strip())
        if offers.get('availability'):
            parts.append(str(offers['availability']).rsplit('/', 1)[-1])
    if product.get('sku'):
        parts.append(f'SKU: {product["sku"]}')
    brand = product.get('brand')
    if isinstance(brand, dict):
        brand = brand.get('name')
    if brand:
        parts.append(f'Brand: {brand}')
    if not parts:
        return ''
    return '**Product:** ' + ' · '.join(parts)


def _jsonld_block(objects):
    if not objects:
        return ''
    payload = objects[0] if len(objects) == 1 else objects
    dumped = json.dumps(payload, indent=2, ensure_ascii=False)
    return f'```json\n{dumped}\n```'


def page_to_agent_markdown(html_content, base_url=''):
    if not html_content:
        return ''
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='replace')
    objects = extract_jsonld(html_content)
    sections = []
    frontmatter = _build_frontmatter(extract_metadata(html_content))
    if frontmatter:
        sections.append(frontmatter)
    summary = _product_summary(objects)
    if summary:
        sections.append(summary)
    body = html_to_markdown(html_content, base_url=base_url)
    if body:
        sections.append(body)
    block = _jsonld_block(objects)
    if block:
        sections.append(block)
    return '\n\n'.join(sections).strip()


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
