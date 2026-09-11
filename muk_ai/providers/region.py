from __future__ import annotations

from typing import NamedTuple


class Region(NamedTuple):
    """One selectable endpoint region for a provider implementation."""

    code: str
    label: str
    url: str | None
    disabled: tuple[str, ...] = ()


CUSTOM = Region('custom', 'Custom URL', None)
