from odoo.tests import BaseCase

from odoo.addons.muk_web_colors.tools import replace_variables

CONTENT = (
    '$mk_color_brand: #243742;\n'
    '$mk_color_primary: #5D8DA8;\n'
    '$o-brand-odoo: $mk_color_brand;\n'
)


class TestColors(BaseCase):
    """Cover replacing the color variables of an SCSS asset."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_replace_rewrites_only_the_declarations(self):
        content = replace_variables(
            CONTENT, {'color_brand': '#112233', 'color_missing': '#000000'}
        )
        self.assertEqual(
            content,
            '$mk_color_brand: #112233;\n'
            '$mk_color_primary: #5D8DA8;\n'
            '$o-brand-odoo: $mk_color_brand;\n',
        )
