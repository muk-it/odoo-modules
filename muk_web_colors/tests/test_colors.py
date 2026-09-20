from odoo.tests import BaseCase

from odoo.addons.muk_web_colors.tools import read_variables, replace_variables

CONTENT = (
    '$mk_color_brand: #243742;\n'
    '$mk_color_primary: #5D8DA8;\n'
    '$o-brand-odoo: $mk_color_brand;\n'
    '$o-brand-primary: $mk_color_primary;\n'
)


class TestColors(BaseCase):
    """Cover reading and replacing the color variables of an SCSS asset."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_read_returns_the_declared_values(self):
        values = read_variables(CONTENT, ['color_brand', 'color_primary'])
        self.assertEqual(values['color_brand'], '#243742')
        self.assertEqual(values['color_primary'], '#5D8DA8')

    def test_read_returns_false_for_an_undeclared_variable(self):
        values = read_variables(CONTENT, ['color_brand', 'color_missing'])
        self.assertEqual(values['color_brand'], '#243742')
        self.assertFalse(values['color_missing'])

    def test_replace_rewrites_only_the_named_declaration(self):
        content = replace_variables(CONTENT, {'color_brand': '#112233'})
        self.assertIn('$mk_color_brand: #112233;', content)
        self.assertIn('$mk_color_primary: #5D8DA8;', content)

    def test_replace_keeps_the_references_to_the_variable(self):
        content = replace_variables(CONTENT, {'color_brand': '#112233'})
        self.assertIn('$o-brand-odoo: $mk_color_brand;', content)

    def test_replace_rewrites_several_variables_at_once(self):
        content = replace_variables(
            CONTENT,
            {'color_brand': '#112233', 'color_primary': '#445566'},
        )
        self.assertIn('$mk_color_brand: #112233;', content)
        self.assertIn('$mk_color_primary: #445566;', content)

    def test_replace_of_an_undeclared_variable_changes_nothing(self):
        self.assertEqual(
            replace_variables(CONTENT, {'color_missing': '#000000'}), CONTENT
        )
