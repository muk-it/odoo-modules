from __future__ import annotations

# The tool schema and the values the adapters accept are generated from this
# one table, so an option can never be offered to the model and then refused
# on the wire.
IMAGE_OPTIONS = {
    'quality': {
        'description': 'Rendering quality. Omit for the model default.',
        'enum': ('low', 'medium', 'high'),
    },
    'background': {
        'description': 'Background handling. Omit for the model default.',
        'enum': ('transparent', 'opaque'),
    },
}
