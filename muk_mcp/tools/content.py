from __future__ import annotations


def normalize_mimetype(mimetype: str | None) -> str:
    """Return the MIME type lowercased and stripped of any parameters."""
    if not mimetype:
        return ''
    return mimetype.lower().split(';', 1)[0].strip()
