from __future__ import annotations

from typing import NamedTuple

FIELD_TYPES = ('boolean', 'selection', 'many2one', 'many2many')
MAX_CANDIDATES = 50
MAX_CHOICES = 255
MAX_LEVELS = 10
MAX_VALUE_CHARS = 1000


class FieldQuestion(NamedTuple):
    """The questions one line asks, and the field value behind each answer label.

    ``values`` maps an answer label to the value it writes: an option or level
    to its selection key or record id, a tag name to its id, "yes" and "no" to
    a boolean. A question that fills no field has no values.
    """

    field: str
    kind: str
    questions: dict
    values: dict
