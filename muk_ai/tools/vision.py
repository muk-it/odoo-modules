from __future__ import annotations

import re

VISION_UNAVAILABLE = (
    'Note: files were produced but cannot be shown to this model; '
    'rely on the textual/structural result instead.'
)


def is_image_block(block) -> bool:
    """Return whether a content block is an MCP image block."""
    return isinstance(block, dict) and block.get('type') == 'image'


def is_blob_block(block) -> bool:
    """Return whether a content block is an MCP resource block with its bytes."""
    return (
        isinstance(block, dict)
        and block.get('type') == 'resource'
        and isinstance(block.get('resource'), dict)
        and 'blob' in block['resource']
    )


def file_specs(result) -> list[dict]:
    """Return the files a tool result carries as ``{data, mimetype, name}``.

    Reads the ``{'images': [{'data', 'mimetype', 'name'}]}`` convention, MCP
    image blocks (``{'type': 'image', 'data', 'mimeType'}``) and MCP resource
    blocks with their bytes (``{'type': 'resource', 'resource': {'blob', ...}}``).
    """
    blocks = []
    if isinstance(result, dict):
        blocks += [
            block for block in result.get('images') or [] if isinstance(block, dict)
        ]
        result = result.get('content')
    if isinstance(result, list):
        blocks += [block for block in result if is_image_block(block)]
        blocks += [block['resource'] for block in result if is_blob_block(block)]
    specs = []
    for block in blocks:
        data = block.get('data') or block.get('data_b64') or block.get('blob')
        if isinstance(data, str) and data:
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


def strip_files(result) -> object:
    """Return the tool result without its file payloads, resources kept by uri."""
    if isinstance(result, list):
        return [
            {
                **block,
                'resource': {
                    key: value
                    for key, value in block['resource'].items()
                    if key != 'blob'
                },
            }
            if is_blob_block(block)
            else block
            for block in result
            if not is_image_block(block)
        ]
    if not isinstance(result, dict):
        return result
    cleaned = {key: value for key, value in result.items() if key != 'images'}
    if isinstance(cleaned.get('content'), list):
        cleaned['content'] = strip_files(cleaned['content'])
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
