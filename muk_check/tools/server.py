from __future__ import annotations

import os

from odoo.tools import config

READABLE_OPTIONS = frozenset(
    {
        'db_name',
        'dbfilter',
        'dev_mode',
        'limit_memory_hard',
        'limit_time_cpu',
        'limit_time_real',
        'list_db',
        'log_level',
        'proxy_mode',
        'workers',
    }
)


def read_option(key: str) -> object:
    """Return a server option, refusing any that is not on the readable list."""
    if key not in READABLE_OPTIONS:
        raise ValueError(f'The server option {key!r} is not readable from a rule.')
    return config[key]


def master_password_is_default() -> bool:
    """Return whether the master password is still the default one."""
    return config.verify_admin_password('admin')


def is_odoo_sh() -> bool:
    """Return whether the server runs on Odoo.sh."""
    return bool(os.environ.get('ODOO_STAGE'))
