from __future__ import annotations

from typing import NamedTuple

from odoo.tools.translate import LazyGettext, LazyTranslate

_lt = LazyTranslate('muk_ai')


class Region(NamedTuple):
    """One selectable endpoint region for a provider implementation."""

    code: str
    label: LazyGettext
    url: str | None
    disabled: tuple[str, ...] = ()


CUSTOM = Region('custom', _lt('Custom URL'), None)
