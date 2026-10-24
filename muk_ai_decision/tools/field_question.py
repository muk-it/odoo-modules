from __future__ import annotations

from typing import NamedTuple

FIELD_TYPES = ('boolean', 'selection', 'many2one', 'many2many')
MAX_CANDIDATES = 50
MAX_CHOICES = 255
MAX_LEVELS = 10
MAX_RECORDS = 100
MAX_VALUE_CHARS = 1000

QUESTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'field': {
            'type': 'string',
            'description': (
                'Field of "model" the question fills: a yes/no, selection, '
                'many2one or tags field. Its values become the options, so no '
                'ids need to be looked up. Omit for a free question.'
            ),
        },
        'key': {
            'type': 'string',
            'description': 'Id the answer comes back under; the field name by default.',
        },
        'type': {
            'type': 'string',
            'enum': ['choice', 'score', 'noul'],
            'description': (
                '"choice" picks one of "options", "score" rates on "levels", '
                '"noul" returns the probability of yes. Derived from "field".'
            ),
        },
        'instructions': {
            'type': 'string',
            'description': 'The question, e.g. "Which team should handle this?".',
        },
        'options': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'choice without field: 2 to 255 option names.',
        },
        'levels': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': 'score: 2 to 10 levels, lowest first, e.g. ["Low", "High"].',
        },
        'candidates': {
            'type': 'string',
            'description': (
                'many2one or tags field: JSON domain on the records it may be set '
                'to, when it has more than 50.'
            ),
        },
    },
}


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
