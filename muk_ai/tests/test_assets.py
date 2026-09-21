from __future__ import annotations

import re
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

MODULE_ROOT = Path(__file__).resolve().parent.parent

# What ``odoo.tools.js_transpiler.is_odoo_module`` looks for.
ODOO_MODULE_RE = re.compile(r'\s*/(\*|/)\s*@odoo-module')


@tagged('post_install', '-at_install', 'muk_ai')
class TestAssetHeaders(TransactionCase):
    """Verify every bundled script declares itself an Odoo module."""

    def test_every_bundled_script_carries_the_module_header(self):
        missing = [
            str(path.relative_to(MODULE_ROOT)).replace('\\', '/')
            for path in sorted((MODULE_ROOT / 'static' / 'src').rglob('*.js'))
            if 'lib' not in path.parts
            and not ODOO_MODULE_RE.match(path.read_text(encoding='utf-8'))
        ]
        self.assertFalse(
            missing,
            'This Odoo does not recognise an ES module on its own, so a file '
            'without the @odoo-module header is served untranspiled and takes '
            'the whole asset bundle down with it: %s' % ', '.join(missing),
        )
