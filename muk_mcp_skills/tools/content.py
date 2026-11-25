from __future__ import annotations


def is_text(raw: bytes) -> bool:
    """Return whether the bytes are UTF-8 text, whatever type they were stored with."""
    try:
        raw.decode()
    except UnicodeDecodeError:
        return False
    return True
