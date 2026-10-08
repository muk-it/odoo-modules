from odoo.tests import TransactionCase, new_test_user


class TestToolLabels(TransactionCase):
    """Verify the names tool cards show for the models and fields a call names."""

    def test_an_employee_gets_the_names_of_models_and_fields(self):
        user = new_test_user(self.env, login='tool-labels', groups='base.group_user')
        labels = (
            self.env['ir.model']
            .with_user(user)
            .ai_tool_labels(
                {
                    'res.partner': ['phone', 'email', 'no_such_field'],
                    'no.such.model': ['name'],
                }
            )
        )
        self.assertEqual(
            labels,
            {
                'res.partner': {
                    'name': 'Contact',
                    'fields': {'phone': 'Phone', 'email': 'Email'},
                }
            },
        )
