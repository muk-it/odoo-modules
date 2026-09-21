from __future__ import annotations

from . import models

from odoo.api import Environment
from odoo.tools import BinaryBytes, file_open


def _setup_module(env: Environment) -> None:
    """Seed the main company appbar image from the default Odoo logo."""
    if env.ref('base.main_company', False):
        with file_open('base/static/img/res_company_logo.png', 'rb') as file:
            env.ref('base.main_company').write(
                {
                    'appbar_image': BinaryBytes(file.read(), filename='logo.png'),
                }
            )
