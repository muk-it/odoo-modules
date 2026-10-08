from __future__ import annotations

import re

VISION_UNAVAILABLE = (
    'Note: images were produced but cannot be shown to this model; '
    'rely on the textual/structural result instead.'
)


def is_image_block(block) -> bool:
    """Return whether a content block is an MCP image block."""
    return isinstance(block, dict) and block.get('type') == 'image'


def image_specs(result) -> list[dict]:
    """Return the images a tool result carries as ``{data, mimetype, name}``.

    Reads the ``{'images': [{'data', 'mimetype', 'name'}]}`` convention and MCP
    image content blocks (``{'type': 'image', 'data', 'mimeType'}``).
    """
    blocks = []
    if isinstance(result, dict):
        blocks += [
            block for block in result.get('images') or [] if isinstance(block, dict)
        ]
        result = result.get('content')
    if isinstance(result, list):
        blocks += [block for block in result if is_image_block(block)]
    specs = []
    for block in blocks:
        if isinstance(data := block.get('data') or block.get('data_b64'), str) and data:
            specs.append(
                {
                    'data': re.sub(r'\s+', '', data),
                    'mimetype': block.get('mimetype')
                    or block.get('mimeType')
                    or 'image/png',
                    'name': block.get('name')
                    or block.get('filename')
                    or 'tool-image.png',
                }
            )
    return specs


def strip_images(result) -> object:
    """Return the tool result without its image payloads."""
    if isinstance(result, list):
        return [block for block in result if not is_image_block(block)]
    if not isinstance(result, dict):
        return result
    cleaned = {key: value for key, value in result.items() if key != 'images'}
    if isinstance(cleaned.get('content'), list):
        cleaned['content'] = strip_images(cleaned['content'])
    return cleaned


def note_vision_unavailable(cleaned) -> object:
    """Tell the model, inside the result, that its images could not be shown."""
    if isinstance(cleaned, dict):
        text = cleaned.get('text')
        note = f'{text}\n{VISION_UNAVAILABLE}' if text else VISION_UNAVAILABLE
        return {**cleaned, 'text': note}
    if isinstance(cleaned, list):
        return [*cleaned, {'type': 'text', 'text': VISION_UNAVAILABLE}]
    return cleaned
