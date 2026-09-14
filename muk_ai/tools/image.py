from __future__ import annotations

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
