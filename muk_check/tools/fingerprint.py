from __future__ import annotations

import hashlib
import re
from pathlib import Path

from odoo.modules.module import get_manifest, get_module_path
from odoo.tools import file_open
from odoo.tools.translate import TranslationFileReader, get_po_paths

MEMORY_ADDRESS = re.compile(r' at 0x[0-9a-fA-F]+')


def digest(parts: list[bytes]) -> str:
    """Return the hash of the given parts."""
    return hashlib.sha256(b'\0'.join(parts)).hexdigest()


def field_argument(key: str, value: object) -> str:
    """Return a field argument as a text that is the same in every process.

    Options compare as a set, since their order needs no upgrade and can depend
    on the hash seed. Memory addresses of nested functions are left out.
    """
    if key == 'selection' and isinstance(value, list | tuple):
        value = sorted(value)
    return MEMORY_ADDRESS.sub('', repr(value))


def upgrade_files(name: str) -> list[bytes]:
    """Return the content of the data files and migration scripts of an addon."""
    root = Path(get_module_path(name))
    paths = [root / data for data in get_manifest(name)['data']]
    for folder in ('migrations', 'upgrades'):
        paths += sorted((root / folder).rglob('*.py'))
    return [path.read_bytes() for path in paths if path.is_file()]


def database_terms(name: str, language: str) -> list[str]:
    """Return the terms of an addon's translation files that a database stores.

    A file that cannot be read counts as its raw content, so changes still show.
    """
    terms = []
    for path in get_po_paths(name, language):
        with file_open(path, 'rb') as po_file:
            try:
                terms += [
                    repr((row['name'], row['src'], row['value']))
                    for row in TranslationFileReader(po_file, fileformat='po')
                    if row['type'] != 'code'
                ]
            except (OSError, UnicodeDecodeError, AttributeError):
                po_file.seek(0)
                terms.append(repr(po_file.read()))
    return terms
