from __future__ import annotations

import re
from collections.abc import Sequence

VARIABLE_PREFIX = 'mk_'


def _declaration(name: str) -> re.Pattern[str]:
    """Return the pattern matching the declaration of one color variable."""
    return re.compile(rf'\${VARIABLE_PREFIX}{re.escape(name)}:\s*([^;]*);')


def read_variables(content: str, names: Sequence[str]) -> dict[str, str | bool]:
    """Return the value declared for each named color variable.

    :return: the value per name, ``False`` where the variable is absent
    """
    found = {name: _declaration(name).search(content) for name in names}
    return {name: match.group(1) if match else False for name, match in found.items()}


def replace_variables(content: str, values: dict[str, str]) -> str:
    """Return the content with each named color variable set to a new value."""
    for name, value in values.items():
        replacement = f'${VARIABLE_PREFIX}{name}: {value};'
        content = _declaration(name).sub(lambda _, text=replacement: text, content)
    return content
